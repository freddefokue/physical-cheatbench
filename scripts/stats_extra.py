"""Extra statistics for the write-up (per route and per model). Usage: python scripts/stats_extra.py runs/main/base"""
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from analyze import blocked_ep, consequential, load  # noqa: E402

ROUTE_OF = {"pins_R": "R", "pins_D": "D", "markers_D": "D", "dose_D": "D", "pins_P": "P", "markers_P": "P",
            "dose_P": "P", "pallet_D": "S-D", "pallet_P": "S-P"}

eps = [r for r in load(sys.argv[1]) if r.get("end_reason") not in ("exception", "budget")]
from analyze import OVERRIDES, ROOT  # noqa: E402
for r in eps:                                   # hand-review overrides (results/label_overrides.json)
    key = str(Path(r["_file"]).resolve().relative_to(ROOT))
    if key in OVERRIDES and r.get("label"):
        r["label"]["cheat_attempt"] = OVERRIDES[key]["cheat_attempt"]
act = [r for r in eps if not blocked_ep(r)]
lab = [r for r in act if r.get("label") and "cheat_attempt" in r["label"]]
print(f"episodes {len(eps)}, acting {len(act)}, labelled {len(lab)}, blocked {len(eps) - len(act)}")

# exposure and honest success per env
ex, hs, n = Counter(), Counter(), Counter()
for r in act:
    n[r["env"]] += 1
    ex[r["env"]] += bool(r.get("exposure"))
    o = r.get("outcome") or {}
    hs[r["env"]] += bool(o.get("true_success")) and not (r.get("label") or {}).get("cheat_attempt")
print("\nper env: exposure / honest true success")
for e in n:
    print(f"  {e:<10} n={n[e]:<4} exposed {ex[e]}/{n[e]}  honest success {hs[e]}/{n[e]}")

# cheating routes actually used, per environment
print("\nroute used (judge) per env")
ru = defaultdict(Counter)
for r in lab:
    l = r["label"]
    if l.get("cheat_attempt"):
        ru[r["env"]][l.get("cheat_route")] += 1
for e, c in ru.items():
    print(f"  {e:<10} {dict(c)}")

# disclosure / misleading among cheaters, by route family
print("\nreports among cheating episodes, by environment route")
d = defaultdict(Counter)
for r in lab:
    l = r["label"]
    if not l.get("cheat_attempt"):
        continue
    k = ROUTE_OF[r["env"]]
    d[k]["n"] += 1
    d[k]["disclosed"] += bool(l.get("disclosed_shortcut"))
    d[k]["misleading"] += bool(l.get("misleading_report"))
    d[k]["claims_success"] += bool(l.get("claims_success"))
    d[k]["consequential"] += consequential(r)
for k, c in d.items():
    print(f"  {k:<4} {dict(c)}")

# disclosure by model (reference route)
print("\nR route: disclosed / cheats, by model")
dm = defaultdict(Counter)
for r in lab:
    l = r["label"]
    if r["env"] == "pins_R" and l.get("cheat_attempt"):
        dm[r["model"]]["n"] += 1
        dm[r["model"]]["disclosed"] += bool(l.get("disclosed_shortcut"))
for m, c in dm.items():
    print(f"  {m:<18} {c['disclosed']}/{c['n']}")

# eval awareness by model
print("\nevaluation awareness by model (labelled acting episodes)")
aw = defaultdict(Counter)
for r in lab:
    aw[r["model"]]["n"] += 1
    aw[r["model"]]["aware"] += bool(r["label"].get("eval_awareness"))
    aw[r["model"]]["aware_cheat"] += bool(r["label"].get("eval_awareness")) and bool(r["label"].get("cheat_attempt"))
for m, c in aw.items():
    print(f"  {m:<18} aware {c['aware']}/{c['n']}  (of which cheated {c['aware_cheat']})")

# blocked episodes by model and env
print("\nblocked by provider classifier")
bl = Counter((r["model"], r["env"]) for r in eps if blocked_ep(r))
for k, v in sorted(bl.items()):
    print(f"  {k[0]:<12} {k[1]:<10} {v}")

# consequences: false records and unsafe production
print("\nconsequences")
fr = Counter()
for r in act:
    if consequential(r):
        fr[(r["model"], r["env"])] += 1
for k, v in sorted(fr.items()):
    print(f"  {k[0]:<18} {k[1]:<10} {v}")
