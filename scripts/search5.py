"""The owner's follow-up search (PLAN_v5.md section 13): run candidate scenes with the v5 harness, unchanged.

Episodes are run by scripts/run5.py's run_episode (the same stock agent, embodiment, transport and record) with the
candidate scene classes of pcb5/elicit.py (and pcb5/teach.py), and written to runs/v5_search/<condition>/<model>/
<scene>_A/<seed>.json, apart from the pre-registered runs. The search budget is checked before every episode.

Usage: python scripts/search5.py --models gpt-6-astra --scenes pack_small,pack_override --seeds 100-102
       [--condition main|honest_ok] [--workers 3] [--out runs/v5_search]
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
SEARCH_BUDGET = 30.0          # USD for the whole follow-up (PLAN_v5.md section 13)


def candidate_scenes():
    from pcb5.elicit import ELICIT_SCENES
    out = dict(ELICIT_SCENES)
    try:
        from pcb5.teach import TEACH_SCENES
        out.update(TEACH_SCENES)
    except ImportError:
        pass
    return out


def spent_on_search(out_root):
    tot = 0.0
    for f in Path(out_root).rglob("*.json"):
        if ".inspect" in f.name:
            continue
        try:
            tot += float(json.loads(f.read_text()).get("cost") or 0.0)
        except (ValueError, OSError):
            pass
    return tot


def run_one(model, scene, condition, seed, out_root, budget=SEARCH_BUDGET):
    import run5
    if scene.startswith("teach"):
        # the teach scene logs commanded taught joint values, which only the cell sees (pcb5/teach.py, TeachCell)
        import pcb5.cell5
        from pcb5.teach import TeachCell
        pcb5.cell5.Workcell5 = TeachCell
    run5.OUT = Path(out_root)
    base = run5.scene_classes
    run5.scene_classes = lambda: dict(base(), **candidate_scenes())
    if spent_on_search(out_root) >= budget:
        return (f"{condition}/{model}/{scene}_A/{seed}", "skipped: search budget used", 0.0, None)
    return run5.run_episode(model, scene, condition, seed)


def _star(j):
    return run_one(*j)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--models", required=True)
    ap.add_argument("--scenes", required=True)
    ap.add_argument("--condition", default="main")
    ap.add_argument("--seeds", default="100-102")
    ap.add_argument("--workers", type=int, default=3)
    ap.add_argument("--out", default=str(ROOT / "runs" / "v5_search"))
    ap.add_argument("--skip-done", action="store_true")
    ap.add_argument("--budget", type=float, default=SEARCH_BUDGET, help="USD for this output folder")
    a = ap.parse_args()
    if not os.environ.get("PCB_CAP_OPENROUTER"):
        sys.exit("set PCB_CAP_OPENROUTER")
    from run5 import seeds
    jobs = []
    for s in seeds(a.seeds):
        for sc in a.scenes.split(","):
            for m in a.models.split(","):
                p = Path(a.out) / a.condition / m / f"{sc}_A" / f"{s}.json"
                if a.skip_done and p.exists() and json.loads(p.read_text()).get("end_reason") in (
                        "final", "provider_refusal", "limit"):
                    continue
                jobs.append((m, sc, a.condition, s, a.out, a.budget))
    print(f"{len(jobs)} episodes; spending so far ${spent_on_search(a.out):.2f} of ${a.budget}", flush=True)
    from multiprocessing import get_context
    with ProcessPoolExecutor(max(1, a.workers), mp_context=get_context("spawn")) as ex:
        for r in ex.map(_star, jobs):
            print(r, flush=True)


if __name__ == "__main__":
    main()
