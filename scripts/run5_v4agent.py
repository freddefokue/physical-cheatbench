"""Comparison variant "v4agent" (PLAN_v5.md, "Comparison with the v4 harness"): v4's agent harness, unchanged
(pcb/agent.py: bash and view_image tools, its system prompt, a final message, 80 tool calls, $6 per episode), on the
v5 guard cell (pcb5/bridge.py, GuardTask5CLI). Records go to runs/v5/cmp_v4agent/<condition>/<model>/guard_A/<seed>.json
in v4's record format.

Usage: python scripts/run5_v4agent.py --models opus-5.5,kimi-k3 --seeds 0-3 [--condition base] [--workers 3]
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
OUT = ROOT / "runs" / "v5" / "cmp_v4agent"


def run_one(model, seed, condition):
    import pcb.agent as A
    import pcb.episode as E
    from pcb5.bridge import GuardTask5CLI
    from pcb5.version import HARNESS_VERSION
    from scripts.run5 import load_env
    load_env()
    E.TASKS["guard5cli"] = GuardTask5CLI
    A.V4_TASKS.add("guard5cli")
    cond_dir = "main" if condition == "base" else condition
    out = OUT / cond_dir / model / "guard_A" / f"{seed}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    rec = A.run_episode(model, "guard5cli", "A", seed, out, condition=condition, max_tool_calls=80, max_cost=6.0)
    rec["variant_v5"] = "v4agent"
    rec["harness_v5"] = HARNESS_VERSION
    out.write_text(json.dumps(rec, indent=1, default=str))
    o = rec.get("outcome") or {}
    return rec["id"], rec.get("end_reason"), round(rec.get("cost") or 0, 4), [a["kind"] for a in o.get("acts", [])]


def _star(j):
    return run_one(*j)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--models", required=True)
    ap.add_argument("--seeds", default="0-3")
    ap.add_argument("--condition", default="base")
    ap.add_argument("--workers", type=int, default=1)
    ap.add_argument("--skip-done", action="store_true")
    a = ap.parse_args()
    if not os.environ.get("PCB_CAP_OPENROUTER"):
        sys.exit("set PCB_CAP_OPENROUTER")
    from scripts.run5 import seeds
    cond_dir = "main" if a.condition == "base" else a.condition
    jobs = []
    for s in seeds(a.seeds):
        for m in a.models.split(","):
            p = OUT / cond_dir / m / "guard_A" / f"{s}.json"
            if a.skip_done and p.exists() and json.loads(p.read_text()).get("end_reason") in ("final", "refusal", "limit"):
                continue
            jobs.append((m, s, a.condition))
    print(f"{len(jobs)} episodes", flush=True)
    if a.workers <= 1:
        for j in jobs:
            print(run_one(*j), flush=True)
    else:
        from multiprocessing import get_context
        with ProcessPoolExecutor(a.workers, mp_context=get_context("spawn"), max_tasks_per_child=1) as ex:
            for r in ex.map(_star, jobs):
                print(r, flush=True)


if __name__ == "__main__":
    main()
