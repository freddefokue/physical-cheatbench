"""One-line-per-condition progress of the v4 main run: finished episodes, end reasons, cost, errors, labels."""
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
TOTAL = {"main": 432, "dont_cheat": 216, "honest_ok": 108, "authorized": 54}
done, ends, cost, errs = Counter(), defaultdict(Counter), Counter(), Counter()
for f in (ROOT / "runs/v4").rglob("*.json"):
    if f.parent.name == "images":
        continue
    try:
        r = json.loads(f.read_text())
    except ValueError:
        continue
    c = r.get("condition")
    done[c] += 1
    ends[c][r.get("end_reason")] += 1
    cost[c] += r.get("cost", 0)
    errs[c] += len(r.get("internal_errors") or [])
lab = ROOT / "results/v4/labels/primary.jsonl"
nlab = sum(1 for _ in open(lab)) if lab.exists() else 0
for c, n in TOTAL.items():
    print(f"{c:11s} {done[c]:3d}/{n}  ${cost[c]:7.2f}  ends {dict(ends[c])}  internal_errors {errs[c]}")
from pcb import ledger
s, o = ledger.totals("openrouter")
print(f"labels: {nlab}; ledger settled ${s:.2f}, open ${o:.2f}")
