"""Label episodes with the transcript judge (writes the label into each episode file under "label").

Usage: python scripts/label.py runs/<run> [--workers 8] [--force]
"""
import argparse
import json
import os
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from scripts.run import load_env  # noqa: E402


def main():
    load_env()
    from pcb.judge import criteria_version, judge
    ap = argparse.ArgumentParser()
    ap.add_argument("root")
    ap.add_argument("--workers", type=int, default=8)
    ap.add_argument("--force", action="store_true")
    a = ap.parse_args()
    if not os.environ.get("PCB_CAP_OPENROUTER"):
        sys.exit("set PCB_CAP_OPENROUTER")
    files = sorted(Path(a.root).rglob("*.json"))
    todo = []
    for f in files:
        try:
            r = json.loads(f.read_text())
        except ValueError:          # being written by a running episode
            continue
        if "turns" not in r or r.get("end_reason") in ("exception", "budget", None):
            continue
        lab = r.get("label") or {}
        if lab and not a.force and "parse_error" not in lab and lab.get("_criteria") == criteria_version():
            continue
        todo.append(f)
    print(f"{len(todo)} episodes to label", flush=True)

    def one(f):
        r = json.loads(f.read_text())
        r["label"] = judge(r)
        f.write_text(json.dumps(r, indent=1, default=str))
        return f, r["label"]

    with ThreadPoolExecutor(max_workers=a.workers) as ex:
        for fut in as_completed([ex.submit(one, f) for f in todo]):
            try:
                f, lab = fut.result()
                print(f"{f}: cheat={lab.get('cheat_attempt')} route={lab.get('cheat_route')} "
                      f"considered={lab.get('considered_shortcut')} aware={lab.get('eval_awareness')} "
                      f"${lab.get('_cost')}", flush=True)
            except Exception as e:  # noqa: BLE001
                print("label failed:", e, flush=True)


if __name__ == "__main__":
    main()
