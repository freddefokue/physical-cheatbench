"""Extract case material for the write-up: for each judge-labelled cheat, the reasoning/text just before the first
qualifying turn, the qualifying command, and the final report. Usage: python scripts/cases.py runs/main/base > results/cases.md"""
import json
import sys
from pathlib import Path

root = Path(sys.argv[1])
out = []
for f in sorted(root.rglob("*.json")):
    r = json.loads(f.read_text())
    lab = r.get("label") or {}
    if not lab.get("cheat_attempt"):
        continue
    turns = lab.get("cheat_turns") or []
    t0 = min(turns) if turns else None
    out.append(f"## {r['model']} / {r['env']} / seed {r['seed']}  (route: {lab.get('cheat_route')}, "
               f"disclosed: {lab.get('disclosed_shortcut')}, misleading report: {lab.get('misleading_report')})")
    out.append(f"Judge note: {lab.get('notes')}")
    if t0 is not None and t0 < len(r["turns"]):
        for t in r["turns"][max(0, t0 - 1): t0 + 1]:
            if t.get("reasoning"):
                out.append(f"- turn {t['i']} reasoning: \"{t['reasoning'][:900].strip()}\"")
            if t.get("text"):
                out.append(f"- turn {t['i']} text: \"{t['text'][:600].strip()}\"")
            for c in t.get("tool_calls", []):
                cmd = c["args"].get("command") if isinstance(c.get("args"), dict) else None
                out.append(f"- turn {t['i']} command: `{(cmd or json.dumps(c.get('args')))[:400]}`")
    out.append(f"- final report: \"{(r.get('final_text') or '')[:1200].strip()}\"")
    out.append("")
print("\n".join(out))
