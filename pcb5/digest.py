"""What an episode's model calls show, in the record's own fields (PLAN_v5.md, "Records").

The agent's transcript is the call log beside the record (<seed>.llm.jsonl: per call, the messages new since the
previous call, with images replaced by markers, and the reply). digest() adds to the record:
  turns            per model reply: reasoning, text and tool calls (name, arguments), as v4's records had them
  calls            per tool call: turn, name, arguments and the tool's reply text
  exposure_routes  per route, the first tool reply that showed the route's pointer (the scene's exposure keys:
                   e.g. the spare actuator's name in a vision listing), or None; as v4 computed it
  canary           the first tool reply that contained protected content (the scene's canaries), or None
"""
import json
from pathlib import Path


def _text(content):
    if isinstance(content, str):
        return content
    out = []
    for part in content or []:
        if isinstance(part, dict):
            if part.get("type") == "text":
                out.append(part.get("text") or "")
            elif part.get("type") == "image":
                out.append("[image]")
    return "\n".join(out)


def load_calls(llm_path):
    p = Path(llm_path)
    if not p.exists():
        return []
    return [json.loads(line) for line in p.read_text().splitlines() if line.strip()]


def digest(rec, llm_path, exposure_keys=None, canaries=None):
    turns, calls, pending = [], [], {}
    for d in load_calls(llm_path):
        for m in d.get("new_messages") or []:
            if m.get("role") == "tool" and m.get("tool_call_id") in pending:
                pending.pop(m["tool_call_id"])["output"] = _text(m.get("content"))
        r = d.get("reply") or {}
        tcs = []
        for tc in r.get("tool_calls") or []:
            fn = tc.get("function") or {}
            try:
                args = json.loads(fn.get("arguments") or "{}")
            except ValueError:
                args = {"_raw": fn.get("arguments")}
            tcs.append({"id": tc.get("id"), "name": fn.get("name"), "args": args})
            c = {"turn": d["i"], "id": tc.get("id"), "name": fn.get("name"), "args": args, "output": None}
            calls.append(c)
            pending[tc.get("id")] = c
        turns.append({"i": d["i"], "reasoning": r.get("reasoning") or "", "text": _text(r.get("content")) or "",
                      "refusal": r.get("refusal"), "tool_calls": tcs, "latency_s": d.get("latency_s"),
                      "cost": d.get("cost") or 0.0, "status": d.get("status")})
    outputs = [c.get("output") or "" for c in calls]

    def first_hit(keys):
        if not keys:
            return None
        for k, (o, c) in enumerate(zip(outputs, calls)):
            if any(key in o for key in keys):
                return {"call": k, "turn": c["turn"]}
        return None
    rec["turns"], rec["calls"] = turns, calls
    rec["exposure_routes"] = {r: first_hit(ks) for r, ks in (exposure_keys or {}).items()}
    rec["canary"] = first_hit(canaries or [])
    return rec
