"""Rerun, once, the pre-registered episodes that ended before the agent acted (PLAN_v5.md section 12, item 1).

An episode is rerun if it ended in an exception, or in an agent error before any of the agent's tool calls executed
(e.g. an empty first response). Its first record is kept beside the new one as <seed>.err.json (with
<seed>.err.llm.jsonl and <seed>.err.inspect.tar.gz). An episode that already has an .err.json is not rerun again.

Usage: python scripts/retry5.py [--conditions main,honest_ok,authorized,dont_cheat] [--dry-run] [--workers 4]
Requires PCB_CAP_OPENROUTER.
"""
import argparse
import json
import os
import sys
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))


def needs_retry(r):
    acted = any(c.get("output") is not None for c in r.get("calls") or [])
    return r.get("end_reason") == "exception" or (r.get("end_reason") == "error" and not acted)


def _star(j):
    import run5
    return run5.run_episode(*j)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--conditions", default="main,honest_ok,authorized,dont_cheat")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--workers", type=int, default=4)
    a = ap.parse_args()
    jobs = []
    for cond in a.conditions.split(","):
        for f in sorted((ROOT / "runs" / "v5" / cond).glob("*/*_A/*.json")):
            if f.name.endswith(".err.json"):
                continue
            r = json.loads(f.read_text())
            if not needs_retry(r) or f.with_name(f.stem + ".err.json").exists():
                continue
            jobs.append((f, r))
    print(f"{len(jobs)} episodes to rerun", flush=True)
    for f, r in jobs:
        print("  ", f.relative_to(ROOT), r.get("end_reason"), (r.get("error") or "")[:120].replace("\n", " "), flush=True)
    if a.dry_run or not jobs:
        return
    if not os.environ.get("PCB_CAP_OPENROUTER"):
        sys.exit("set PCB_CAP_OPENROUTER")
    runs = []
    for f, r in jobs:
        stem = f.with_suffix("")
        for src, dst in ((f, f.with_name(f.stem + ".err.json")),
                         (Path(str(stem) + ".llm.jsonl"), Path(str(stem) + ".err.llm.jsonl")),
                         (Path(str(stem) + ".inspect.tar.gz"), Path(str(stem) + ".err.inspect.tar.gz"))):
            if src.exists():
                src.rename(dst)
        runs.append((r["model"], r["task"], r["condition"], r["seed"], r.get("max_llm_calls", 100), r.get("control_hz", 25.0)))
    from multiprocessing import get_context
    with ProcessPoolExecutor(max(1, a.workers), mp_context=get_context("spawn")) as ex:
        for res in ex.map(_star, runs):
            print(res, flush=True)


if __name__ == "__main__":
    main()
