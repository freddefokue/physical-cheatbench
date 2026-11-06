"""Episodes for the independent judge (PLAN_v4.md section 5): a random 25 % of the acting, unblocked episodes of
every condition, stratified by scene (seed 2026). Writes results/v4/independent_sample.txt.
Usage: python scripts/sample_independent4.py [--run v4]
"""
import argparse
import random
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))
import analyze4 as A  # noqa: E402
from pcb import classify4  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--run", default="v4")
    a = ap.parse_args()
    by = defaultdict(list)
    for r in A.load_eps(a.run):
        lab = classify4.classify(r, None, use_judge=False)
        if lab["blocked"] or not A.acting(r):
            continue
        by[r["task"]].append(r["_rel"])
    rng = random.Random(2026)
    picked = []
    for sc in sorted(by):
        files = sorted(by[sc])
        picked += rng.sample(files, round(len(files) * 0.25))
    out = A.OUT / "independent_sample.txt"
    out.write_text("\n".join(sorted(picked)) + "\n")
    print(f"{len(picked)} of {sum(map(len, by.values()))} episodes -> {out}")


if __name__ == "__main__":
    main()
