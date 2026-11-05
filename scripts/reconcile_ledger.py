"""Close reservations left open by killed processes, at a total cost taken from the provider's own usage figures.

Usage: python scripts/reconcile_ledger.py --provider openrouter --billed 1.79 --note "..."  [--dry-run]
The billed amount is split over the open reservations in proportion to their reserved upper bounds and written as
"settle" records tagged reconcile, so caps stop counting the killed calls at their upper bounds.
"""
import argparse
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from pcb import ledger  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--provider", required=True)
    ap.add_argument("--billed", type=float, required=True)
    ap.add_argument("--note", required=True)
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()
    with ledger._locked():
        c = ledger._refresh()
        opened = {rid: amt for rid, (p, amt) in c["open"].items() if p == a.provider}
        total = sum(opened.values())
        print(f"{len(opened)} open reservations, ${total:.2f} reserved; settling at ${a.billed:.2f} in total")
        if a.dry_run or not opened:
            return
        for rid, amt in opened.items():
            ledger._append({"t": round(time.time(), 1), "kind": "settle", "rid": rid, "provider": a.provider,
                            "model": "?", "tag": f"reconcile: {a.note}", "usage": {},
                            "cost": round(a.billed * amt / total, 6)})


if __name__ == "__main__":
    main()
