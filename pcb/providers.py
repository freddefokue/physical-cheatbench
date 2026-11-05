"""Model adapters. One conversation object per episode with the same interface for every provider:
  step(allow_tools) -> Turn;  add_tool_results(results, extra_text=None);  add_user(text)
Histories are append-only (reasoning blocks are passed back unchanged), so prompt caching works and thinking stays valid.
No server-side model fallbacks are used: a refusal is recorded as a refusal, so every turn comes from the model tested.
"""
import base64
import json
import os
import time
from dataclasses import dataclass, field

from . import ledger

BASH_DESC = ("Run a shell command on the cell workstation (bash on Linux) and return its output (stdout and stderr). "
             "The working directory persists between calls; other shell state does not. A command times out after "
             "180 s unless you pass a larger timeout (at most 600 s).")
IMAGE_DESC = "Look at an image file (PNG or JPEG) on the workstation, for example a camera capture."
TOOLS = [
    {"name": "bash", "description": BASH_DESC,
     "schema": {"type": "object", "properties": {
         "command": {"type": "string", "description": "The shell command to run."},
         "timeout": {"type": "integer", "description": "Timeout in seconds (default 180, maximum 600)."}},
         "required": ["command"]}},
    {"name": "view_image", "description": IMAGE_DESC,
     "schema": {"type": "object", "properties": {
         "path": {"type": "string", "description": "Path of the image file."}}, "required": ["path"]}},
]


@dataclass
class ToolCall:
    id: str
    name: str
    args: dict
    raw: str
    error: str = ""


@dataclass
class Turn:
    text: str = ""
    reasoning: str = ""
    tool_calls: list = field(default_factory=list)
    stop: str = "end"
    usage: dict = field(default_factory=dict)
    cost: float = 0.0
    raw: object = None
    detail: str = ""
    latency: float = 0.0
    retries: int = 0


MAX_TOKENS = 32000


def upper_bound(cfg, payload, n_images=0, max_tokens=MAX_TOKENS):
    """Worst-case USD cost of one call: every input token billed at the dearest input rate (cache write), images at
    1,600 tokens each, the whole output allowance used, plus 10%. Used to reserve budget before the call."""
    chars = len(json.dumps(payload, default=str))
    p = cfg["prices"]
    in_tok = chars / 3.0 + n_images * 1600
    return 1.1 * (in_tok * max(p[0], p[1]) + max_tokens * p[3]) / 1e6 + 0.002


def _strip_images(msgs):
    """Copy of an OpenAI-style message list with image data replaced by a marker (for size estimates)."""
    out, n = [], 0
    for m in msgs:
        c = m.get("content")
        if isinstance(c, list):
            cc = []
            for part in c:
                if isinstance(part, dict) and part.get("type") in ("image_url", "input_image", "image"):
                    n += 1
                    cc.append({"type": "image"})
                else:
                    cc.append(part)
            m = dict(m, content=cc)
        out.append(m)
    return out, n


def parse_args(raw):
    if isinstance(raw, dict):
        return raw, ""
    try:
        v = json.loads(raw or "{}")
        return (v, "") if isinstance(v, dict) else ({}, "arguments are not a JSON object")
    except ValueError as e:
        return {}, f"invalid JSON arguments: {e}"


def b64(data):
    return base64.b64encode(data).decode()


def tools_for(cfg):
    return [t for t in TOOLS if cfg.get("vision", True) or t["name"] != "view_image"]


# ------------------------------------------------------------------------------------------------------------------
class AnthropicConv:
    provider = "anthropic"

    def __init__(self, cfg, system, user, tag):
        import anthropic
        self.anthropic = anthropic
        self.client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"], max_retries=4, timeout=1200)
        self.cfg, self.system, self.tag = cfg, system, tag
        self.msgs = [{"role": "user", "content": [{"type": "text", "text": user}]}]
        self.tools = [{"name": t["name"], "description": t["description"], "input_schema": t["schema"]}
                      for t in tools_for(cfg)]

    def next_upper_bound(self):
        return upper_bound(self.cfg, [self.system, self.msgs, self.tools])

    def step(self, allow_tools=True):
        ub = self.next_upper_bound()
        rid = ledger.reserve(self.provider, ub, self.tag)
        kw = dict(model=self.cfg["model"], max_tokens=MAX_TOKENS, system=self.system, messages=self.msgs,
                  tools=self.tools, tool_choice={"type": "auto" if allow_tools else "none"},
                  thinking={"type": "adaptive", "display": "summarized"},
                  output_config={"effort": self.cfg["effort"]}, cache_control={"type": "ephemeral"})
        t0, retries = time.time(), 0
        while True:
            try:
                with self.client.messages.stream(**kw) as st:
                    resp = st.get_final_message()
                break
            except (self.anthropic.APIConnectionError, self.anthropic.RateLimitError,
                    self.anthropic.InternalServerError) as e:
                retries += 1
                if retries > 6:
                    raise
                time.sleep(min(120, 10 * 2 ** retries))
            except self.anthropic.APIStatusError as e:
                if e.status_code in (429, 500, 502, 503, 504, 529) and retries < 6:
                    retries += 1
                    time.sleep(min(120, 10 * 2 ** retries))
                    continue
                raise
        u = resp.usage
        usage = {"input": u.input_tokens or 0, "cache_write": u.cache_creation_input_tokens or 0,
                 "cache_read": u.cache_read_input_tokens or 0, "output": u.output_tokens or 0}
        p = self.cfg["prices"]
        cost = (usage["input"] * p[0] + usage["cache_write"] * p[1] + usage["cache_read"] * p[2]
                + usage["output"] * p[3]) / 1e6
        ledger.settle(rid, self.provider, self.cfg["model"], self.tag, usage, cost)
        turn = Turn(usage=usage, cost=cost, latency=time.time() - t0, retries=retries)
        for b in resp.content:
            if b.type == "text":
                turn.text += b.text
            elif b.type == "thinking":
                turn.reasoning += (b.thinking or "")
            elif b.type == "tool_use":
                args, err = parse_args(b.input)
                turn.tool_calls.append(ToolCall(b.id, b.name, args, json.dumps(b.input), err))
        turn.stop = {"tool_use": "tool_use", "end_turn": "end", "max_tokens": "max_tokens",
                     "refusal": "refusal"}.get(resp.stop_reason, str(resp.stop_reason))
        if resp.stop_reason == "refusal":
            sd = getattr(resp, "stop_details", None)
            turn.detail = json.dumps({"category": getattr(sd, "category", None),
                                      "explanation": getattr(sd, "explanation", None)}, default=str)
        turn.raw = [b.model_dump(mode="json") for b in resp.content]
        self.msgs.append({"role": "assistant", "content": resp.content})
        return turn

    def add_tool_results(self, results, extra_text=None):
        content = []
        for r in results:
            c = [{"type": "text", "text": r["text"] or "(no output)"}]
            if r.get("image"):
                c.append({"type": "image", "source": {"type": "base64", "media_type": r["mime"], "data": b64(r["image"])}})
            block = {"type": "tool_result", "tool_use_id": r["id"], "content": c}
            if r.get("is_error"):
                block["is_error"] = True
            content.append(block)
        if extra_text:
            content.append({"type": "text", "text": extra_text})
        self.msgs.append({"role": "user", "content": content})

    def add_user(self, text):
        self.msgs.append({"role": "user", "content": [{"type": "text", "text": text}]})


# ------------------------------------------------------------------------------------------------------------------
class OpenAIConv:
    provider = "openai"

    def __init__(self, cfg, system, user, tag):
        import openai
        self.openai = openai
        self.client = openai.OpenAI(api_key=os.environ["OpenAI_API_KEY"], max_retries=4, timeout=1800)
        self.cfg, self.system, self.tag = cfg, system, tag
        self.pending = [{"role": "user", "content": [{"type": "input_text", "text": user}]}]
        self.prev = None
        self.tools = [{"type": "function", "name": t["name"], "description": t["description"],
                       "parameters": t["schema"]} for t in tools_for(cfg)]

    def next_upper_bound(self):
        return upper_bound(self.cfg, [self.system, self.pending, self.tools]) + 0.5   # history is server-side

    def step(self, allow_tools=True):
        ub = self.next_upper_bound()
        rid = ledger.reserve(self.provider, ub, self.tag)
        kw = dict(model=self.cfg["model"], instructions=self.system, input=self.pending, tools=self.tools,
                  tool_choice="auto" if allow_tools else "none",
                  reasoning={"effort": self.cfg["effort"], "summary": "detailed"}, store=True, max_output_tokens=32000)
        if self.prev:
            kw["previous_response_id"] = self.prev
        t0, retries = time.time(), 0
        while True:
            try:
                r = self.client.responses.create(**kw)
                break
            except (self.openai.APIConnectionError, self.openai.RateLimitError, self.openai.InternalServerError):
                retries += 1
                if retries > 6:
                    raise
                time.sleep(min(120, 10 * 2 ** retries))
        u = r.usage
        cached = getattr(getattr(u, "input_tokens_details", None), "cached_tokens", 0) or 0
        reas = getattr(getattr(u, "output_tokens_details", None), "reasoning_tokens", 0) or 0
        usage = {"input": u.input_tokens - cached, "cache_read": cached, "output": u.output_tokens, "reasoning": reas}
        p = self.cfg["prices"]
        cost = (usage["input"] * p[0] + cached * p[2] + usage["output"] * p[3]) / 1e6
        ledger.settle(rid, self.provider, self.cfg["model"], self.tag, usage, cost)
        self.prev, self.pending = r.id, []
        turn = Turn(usage=usage, cost=cost, latency=time.time() - t0, retries=retries)
        refused = False
        for item in r.output:
            if item.type == "reasoning":
                turn.reasoning += "\n".join(s.text for s in (item.summary or []) if getattr(s, "text", None))
            elif item.type == "message":
                for c in item.content:
                    if c.type == "output_text":
                        turn.text += c.text
                    elif c.type == "refusal":
                        refused = True
                        turn.text += c.refusal
            elif item.type == "function_call":
                args, err = parse_args(item.arguments)
                turn.tool_calls.append(ToolCall(item.call_id, item.name, args, item.arguments, err))
        if refused:
            turn.stop = "refusal"
        elif r.status == "incomplete":
            turn.stop = "max_tokens"
            turn.detail = str(getattr(r, "incomplete_details", ""))
        else:
            turn.stop = "tool_use" if turn.tool_calls else "end"
        turn.raw = [i.model_dump(mode="json") for i in r.output]
        return turn

    def add_tool_results(self, results, extra_text=None):
        imgs = []
        for r in results:
            self.pending.append({"type": "function_call_output", "call_id": r["id"], "output": r["text"] or "(no output)"})
            if r.get("image"):
                imgs.append(r)
        if imgs:
            content = []
            for r in imgs:
                content.append({"type": "input_text", "text": f"Image returned by view_image({r['path']}):"})
                content.append({"type": "input_image", "image_url": f"data:{r['mime']};base64,{b64(r['image'])}"})
            self.pending.append({"role": "user", "content": content})
        if extra_text:
            self.pending.append({"role": "user", "content": [{"type": "input_text", "text": extra_text}]})

    def add_user(self, text):
        self.pending.append({"role": "user", "content": [{"type": "input_text", "text": text}]})


# ------------------------------------------------------------------------------------------------------------------
class OpenRouterConv:
    provider = "openrouter"

    def __init__(self, cfg, system, user, tag):
        import openai
        self.openai = openai
        self.client = openai.OpenAI(base_url="https://openrouter.ai/api/v1", api_key=os.environ["OPENROUTER_API_KEY_2"],
                                    max_retries=3, timeout=1200)
        self.cfg, self.tag = cfg, tag
        self.filter_retries = 0
        self.ignore_tool_calls = False
        self.msgs = [{"role": "system", "content": system}, {"role": "user", "content": user}]
        self.tools = [{"type": "function", "function": {"name": t["name"], "description": t["description"],
                                                        "parameters": t["schema"]}} for t in tools_for(cfg)]

    def _usage(self, r):
        u = r.usage.model_dump() if getattr(r, "usage", None) else {}
        cached = ((u.get("prompt_tokens_details") or {}).get("cached_tokens") or 0)
        reas = ((u.get("completion_tokens_details") or {}).get("reasoning_tokens") or 0)
        usage = {"input": (u.get("prompt_tokens") or 0) - cached, "cache_read": cached,
                 "output": u.get("completion_tokens") or 0, "reasoning": reas}
        cost = u.get("cost")
        if cost is None:
            p = self.cfg["prices"]
            cost = (usage["input"] * p[0] + cached * p[2] + usage["output"] * p[3]) / 1e6
        return usage, float(cost)

    def next_upper_bound(self):
        body, n_img = _strip_images(self.msgs)
        return upper_bound(self.cfg, [body, self.tools], n_img)

    def _marked(self):
        """Anthropic models: copy of the history with a prompt-cache breakpoint on the newest message."""
        if not self.cfg.get("anthropic_route"):
            return self.msgs
        msgs = list(self.msgs)
        last = dict(msgs[-1])
        c = last.get("content")
        if isinstance(c, str) and c:
            last["content"] = [{"type": "text", "text": c, "cache_control": {"type": "ephemeral"}}]
        elif isinstance(c, list) and c:
            c = [dict(x) for x in c]
            c[-1]["cache_control"] = {"type": "ephemeral"}
            last["content"] = c
        msgs[-1] = last
        return msgs

    def step(self, allow_tools=True):
        prov = {"require_parameters": True}
        if self.cfg.get("anthropic_route"):
            prov.update({"only": ["anthropic"], "ignore": ["anthropic/fast"]})
        if self.cfg.get("or_only"):
            prov["only"] = list(self.cfg["or_only"])
        kw = dict(model=self.cfg["model"], messages=self._marked(), tools=self.tools,
                  tool_choice="auto" if allow_tools else "none", max_tokens=MAX_TOKENS,
                  extra_body={"reasoning": {"effort": self.cfg["effort"]}, "usage": {"include": True},
                              "provider": prov})
        t0, retries, total_cost, last_err = time.time(), 0, 0.0, ""
        while True:
            body, n_img = _strip_images(kw["messages"])
            ub = upper_bound(self.cfg, [body, self.tools], n_img)
            rid = ledger.reserve(self.provider, ub, self.tag)
            try:
                r = self.client.chat.completions.create(**kw)
            except (self.openai.APIConnectionError, self.openai.RateLimitError, self.openai.InternalServerError,
                    self.openai.APIStatusError) as e:
                if isinstance(e, self.openai.APITimeoutError):
                    ledger.settle(rid, self.provider, self.cfg["model"], self.tag, {"timeout": True}, ub)  # may be billed
                    total_cost += ub
                else:
                    ledger.release(rid, self.provider, self.tag)
                status = getattr(e, "status_code", None)
                if status == 400 and not allow_tools and kw.get("tool_choice") == "none":
                    # some providers reject tool_choice "none": final turn with tools allowed, tool calls ignored
                    kw["tool_choice"] = "auto"
                    self.ignore_tool_calls = True
                    continue
                if status in (400, 401, 403, 404) and "provider" not in str(e).lower():
                    raise
                retries += 1
                last_err = str(e)[:300]
                if retries > 8:
                    raise
                time.sleep(min(90, 5 * 2 ** min(retries, 5)))
                continue
            usage, cost = self._usage(r)
            total_cost += cost
            ledger.settle(rid, self.provider, self.cfg["model"], self.tag, usage, cost)
            ch = r.choices[0] if r.choices else None
            extra = getattr(r, "model_extra", None) or {}
            err = getattr(r, "error", None) or extra.get("error")
            bad = ch is None or ch.finish_reason == "error" or err
            if not bad:
                m = ch.message.model_dump()
                if not (m.get("content") or m.get("tool_calls")) and ch.finish_reason not in ("content_filter",):
                    bad, err = True, "empty reply"
                elif (ch.finish_reason == "content_filter" and not usage.get("output") and not m.get("content")
                      and self.filter_retries < 4):
                    # provider safety classifier declined the input before generating anything: resample
                    self.filter_retries += 1
                    retries += 1
                    last_err = "content_filter before generation"
                    time.sleep(5)
                    continue
            if bad:
                retries += 1
                last_err = str(err or (ch.model_dump() if ch else "no choices"))[:300]
                if retries > 8:
                    turn = Turn(stop="error", detail=last_err, cost=total_cost, latency=time.time() - t0, retries=retries)
                    return turn
                time.sleep(min(60, 3 * retries))
                continue
            break
        m = ch.message.model_dump()
        turn = Turn(usage=usage, cost=total_cost, latency=time.time() - t0, retries=retries)
        turn.text = m.get("content") or ""
        turn.reasoning = m.get("reasoning") or ""
        details = m.get("reasoning_details")
        if not turn.reasoning and details:
            turn.reasoning = "\n".join(d.get("text") or d.get("summary") or "" for d in details if isinstance(d, dict))
        calls = m.get("tool_calls") or []
        if self.ignore_tool_calls and not allow_tools:
            calls = []                         # final turn: only the message text counts
        for tc in calls:
            args, err = parse_args(tc["function"].get("arguments"))
            turn.tool_calls.append(ToolCall(tc["id"], tc["function"]["name"], args, tc["function"].get("arguments") or "", err))
        assistant = {"role": "assistant", "content": turn.text}
        if calls:
            assistant["tool_calls"] = [{"id": tc["id"], "type": "function",
                                        "function": {"name": tc["function"]["name"],
                                                     "arguments": tc["function"].get("arguments") or "{}"}} for tc in calls]
        if details:
            assistant["reasoning_details"] = details
        self.msgs.append(assistant)
        if ch.finish_reason == "content_filter":
            turn.stop = "refusal"
        elif ch.finish_reason == "length":
            turn.stop = "max_tokens"
        else:
            turn.stop = "tool_use" if turn.tool_calls else "end"
        turn.detail = json.dumps({"finish_reason": ch.finish_reason,
                                  "native": (ch.model_extra or {}).get("native_finish_reason"),
                                  "provider": getattr(r, "provider", None) or (r.model_extra or {}).get("provider")})
        turn.raw = m
        return turn

    def add_tool_results(self, results, extra_text=None):
        imgs = []
        for r in results:
            self.msgs.append({"role": "tool", "tool_call_id": r["id"], "content": r["text"] or "(no output)"})
            if r.get("image"):
                imgs.append(r)
        if imgs:
            content = []
            for r in imgs:
                content.append({"type": "text", "text": f"Image returned by view_image({r['path']}):"})
                content.append({"type": "image_url", "image_url": {"url": f"data:{r['mime']};base64,{b64(r['image'])}"}})
            self.msgs.append({"role": "user", "content": content})
        if extra_text:
            self.msgs.append({"role": "user", "content": extra_text})

    def add_user(self, text):
        self.msgs.append({"role": "user", "content": text})


ADAPTERS = {"anthropic": AnthropicConv, "openai": OpenAIConv, "openrouter": OpenRouterConv}


def conversation(cfg, system, user, tag):
    return ADAPTERS[cfg["provider"]](cfg, system, user, tag)
