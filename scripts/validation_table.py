"""Markdown table of results/v4/validation.json (scripted policies, PLAN_v4.md section 4)."""
import json
import sys
from collections import OrderedDict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
rows = json.loads((ROOT / "results/v4/validation.json").read_text())
order = ["spring", "leak4", "pack", "guard", "aloha", "round"]
agg = OrderedDict()
for r in sorted(rows, key=lambda r: (order.index(r["scene"]), r["cond"] != "honest_ok", r["policy"])):
    k = (r["scene"], r["cond"], r["policy"])
    g = agg.setdefault(k, {"n": 0, "pass": 0, "true": 0, "false": 0, "err": 0})
    g["n"] += 1
    passed = r.get("passed") if r["scene"] == "spring" else r.get("check")
    g["pass"] += bool(passed)
    g["true"] += bool(r.get("true")) if r["scene"] != "spring" or r["policy"] != "cheat" else 0
    g["false"] += bool(r.get("false_pass")) or (r["scene"] == "spring" and r["policy"] == "cheat" and bool(passed))
    g["err"] += "error" in r
out = ["| Scene | Condition | Scripted policy | Check passed | True success | False pass |", "|---|---|---|---|---|---|"]
for (sc, c, p), g in agg.items():
    out.append(f"| {sc} | {c} | {p} | {g['pass']}/{g['n']} | {g['true']}/{g['n']} | {g['false']}/{g['n']} |")
print("\n".join(out))
