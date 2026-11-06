"""The agent's model calls go through this httpx transport (PLAN_v5.md, "Harness").

The stock Inspect Robots agent talks to an OpenAI-compatible endpoint (OpenRouter here) with its own httpx client;
it accepts a custom transport. This transport changes nothing the model sees. For every chat completion it:
- reserves the call's worst-case cost in the project ledger first (pcb/ledger.py; the call is refused past the cap)
  and settles it with the cost OpenRouter returns;
- pins the serving provider per model, as v4 did (pcb/models.py), and asks OpenRouter for the usage cost;
- writes the request (images replaced by a marker) and the reply to a JSONL log beside the episode, which is the
  transcript the judges read.
"""
import json
import time
from pathlib import Path

import httpx

from pcb import ledger
from pcb.models import MODELS

IMAGE_TOKENS = 1600


def model_cfg(model_id):
    for key, cfg in MODELS.items():
        if cfg["model"] == model_id:
            return key, cfg
    raise KeyError(f"no pcb/models.py entry for {model_id}")


def _cache_breakpoints(messages):
    """Anthropic prompt caching through OpenRouter: an ephemeral breakpoint on the system message and on the newest
    message (as v4's harness did, pcb/providers.py). The content the model reads is unchanged."""
    out = [dict(m) for m in messages]
    for k in ([0] if out and out[0].get("role") == "system" else []) + ([len(out) - 1] if out else []):
        c = out[k].get("content")
        if isinstance(c, str) and c:
            out[k]["content"] = [{"type": "text", "text": c, "cache_control": {"type": "ephemeral"}}]
        elif isinstance(c, list) and c:
            c = [dict(x) for x in c]
            c[-1]["cache_control"] = {"type": "ephemeral"}
            out[k]["content"] = c
    return out


def _strip_images(messages):
    """Messages with image data replaced by a marker; and the number of images."""
    out, n = [], 0
    for m in messages:
        c = m.get("content")
        if isinstance(c, list):
            cc = []
            for part in c:
                if isinstance(part, dict) and part.get("type") in ("image_url", "input_image", "image"):
                    n += 1
                    cc.append({"type": "image", "note": "image omitted from the log"})
                else:
                    cc.append(part)
            m = dict(m, content=cc)
        out.append(m)
    return out, n


class LedgerTransport(httpx.BaseTransport):
    def __init__(self, log_path, tag, max_tokens=16000):
        self.inner = httpx.HTTPTransport(retries=2)
        self.log_path = Path(log_path)
        self.tag = tag
        self.max_tokens = max_tokens
        self.calls = 0
        self.cost = 0.0
        self.seen = 0                     # messages already logged (each call logs only the new ones)

    def handle_request(self, request):
        if request.method != "POST" or not request.url.path.endswith("/chat/completions"):
            return self.inner.handle_request(request)
        body = json.loads(request.content)
        key, cfg = model_cfg(body.get("model"))
        if cfg.get("anthropic_route"):
            body["provider"] = {"only": ["anthropic"], "ignore": ["anthropic/fast"], "allow_fallbacks": False}
            body["messages"] = _cache_breakpoints(body.get("messages", []))
        elif cfg.get("or_only"):
            body["provider"] = {"only": list(cfg["or_only"]), "allow_fallbacks": False}
        body["usage"] = {"include": True}
        if "reasoning_effort" in body and "reasoning" not in body:
            body["reasoning"] = {"effort": body.pop("reasoning_effort")}
        body.setdefault("max_tokens", self.max_tokens)
        logged, n_img = _strip_images(body.get("messages", []))
        chars = len(json.dumps(logged)) + len(json.dumps(body.get("tools", [])))
        p = cfg["prices"]
        bound = 1.1 * ((chars / 3.0 + n_img * IMAGE_TOKENS) * max(p[0], p[1]) + body["max_tokens"] * p[3]) / 1e6 + 0.002
        rid = ledger.reserve("openrouter", bound, f"run5/{self.tag}")
        content = json.dumps(body).encode()
        headers = dict(request.headers)
        headers["content-length"] = str(len(content))
        req = httpx.Request("POST", request.url, headers=headers, content=content)
        t0 = time.time()
        try:
            resp = self.inner.handle_request(req)
            raw = resp.read()
        except Exception:
            ledger.release(rid, "openrouter", f"run5/{self.tag}")
            raise
        cost, usage, reply = 0.0, {}, None
        try:
            data = json.loads(raw)
            usage = data.get("usage") or {}
            cost = float(usage.get("cost") or 0.0)
            reply = (data.get("choices") or [{}])[0].get("message")
        except (ValueError, AttributeError, IndexError):
            data = None
        if resp.status_code >= 400 and not cost:
            ledger.release(rid, "openrouter", f"run5/{self.tag}")
        else:
            ledger.settle(rid, "openrouter", body.get("model"), f"run5/{self.tag}",
                          {"input": usage.get("prompt_tokens"), "output": usage.get("completion_tokens")}, cost)
        self.calls += 1
        self.cost += cost
        with self.log_path.open("a") as f:
            f.write(json.dumps({"i": self.calls, "t": round(t0, 2), "latency_s": round(time.time() - t0, 2),
                                "status": resp.status_code, "model": body.get("model"), "messages_in": len(logged),
                                "new_messages": logged[self.seen:], "n_images": n_img, "reply": reply,
                                "usage": usage, "cost": cost,
                                "error": None if resp.status_code < 400 else raw[:800].decode("utf-8", "replace")},
                               default=str) + "\n")
        self.seen = len(logged)
        headers = [(k, v) for k, v in resp.headers.items()
                   if k.lower() not in ("content-encoding", "content-length", "transfer-encoding")]
        return httpx.Response(resp.status_code, headers=headers, content=raw, request=request)
