"""Run episodes: models x environments x seeds (x condition), in parallel, resumable.

Example: python scripts/run.py --run pilot --models gemini-3.8-flash --envs pins_R,dose_P --seeds 0-1 --workers 4
Spending caps (USD, required): PCB_CAP_ANTHROPIC, PCB_CAP_OPENAI, PCB_CAP_OPENROUTER.
"""
import argparse
import json
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ.setdefault("MUJOCO_GL", "egl")


def load_env():
    for line in (ROOT / ".env").read_text().splitlines():
        if "=" in line and not line.strip().startswith("#"):
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip())


def seeds(spec):
    out = []
    for part in spec.split(","):
        if "-" in part:
            a, b = part.split("-")
            out += list(range(int(a), int(b) + 1))
        else:
            out.append(int(part))
    return out


def main():
    load_env()
    from pcb import ledger
    from pcb.agent import run_episode
    from pcb.episode import ALL_ENVS, ENVS, env_id
    ap = argparse.ArgumentParser()
    ap.add_argument("--run", required=True)
    ap.add_argument("--models", required=True)
    ap.add_argument("--envs", default="all")
    ap.add_argument("--seeds", default="0-9")
    ap.add_argument("--condition", default="base")
    ap.add_argument("--workers", type=int, default=6)
    ap.add_argument("--max-tool-calls", type=int, default=50)
    ap.add_argument("--max-cost", type=float, default=6.0)
    ap.add_argument("--keep-fs", action="store_true")
    a = ap.parse_args()
    for p in ("ANTHROPIC", "OPENAI", "OPENROUTER"):
        if not os.environ.get(f"PCB_CAP_{p}"):
            sys.exit(f"set PCB_CAP_{p}")
    envs = ENVS if a.envs == "all" else [e for e in ALL_ENVS if env_id(*e) in a.envs.split(",")]
    jobs = []
    for m in a.models.split(","):
        for s in seeds(a.seeds):
            for t, v in envs:
                out = ROOT / "runs" / a.run / a.condition / m / env_id(t, v) / f"{s}.json"
                if out.exists():
                    try:
                        if json.loads(out.read_text()).get("end_reason") not in ("exception", "budget", None):
                            continue
                    except ValueError:
                        pass
                jobs.append((m, t, v, s, out))
    import random
    random.Random(12345).shuffle(jobs)          # interleave models and environments
    print(f"{len(jobs)} episodes to run; spent so far: " + ", ".join(
        f"{p} ${ledger.spent(p):.2f}/{ledger.cap(p):.0f}" for p in ("anthropic", "openai", "openrouter")), flush=True)
    t0 = time.time()
    done = 0
    with ThreadPoolExecutor(max_workers=a.workers) as ex:
        futs = {ex.submit(run_episode, m, t, v, s, out, a.condition, a.max_tool_calls, a.max_cost, a.keep_fs):
                (m, t, v, s) for m, t, v, s, out in jobs}
        for f in as_completed(futs):
            m, t, v, s = futs[f]
            done += 1
            try:
                r = f.result()
                o = r.get("outcome", {})
                fl = [k for k, val in (o.get("flags") or {}).items() if val]
                print(f"[{done}/{len(jobs)} {time.time() - t0:5.0f}s] {m:<18} {t}_{v} s{s}: {r.get('end_reason')}, "
                      f"{r.get('n_tool_calls')} calls, ${r.get('cost', 0):.3f}, exposure={bool(r.get('exposure'))}, "
                      f"true={o.get('true_success')}, flags={fl} {r.get('error', '')[:120]}", flush=True)
            except Exception as e:  # noqa: BLE001
                print(f"[{done}/{len(jobs)}] {m} {t}_{v} s{s}: crashed {e}", flush=True)
    print("spent: " + ", ".join(f"{p} ${ledger.spent(p):.2f}" for p in ("anthropic", "openai", "openrouter")))


if __name__ == "__main__":
    main()
