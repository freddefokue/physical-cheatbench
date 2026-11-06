"""Episodes for the independent judge (PLAN_v3.md section 4): every acting, unblocked episode with any logged act or
any positive primary-judge route field (noticed, intent, acted), plus a random third of the rest (seed 2026).
Writes results/v3/independent_sample.txt (one repository-relative path per line).
Usage: python scripts/sample_independent3.py [--run v3]
"""
import argparse
import random
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))
import analyze3 as A  # noqa: E402
from pcb import classify3  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--run", default="v3")
    a = ap.parse_args()
    eps = A.load_eps(a.run)
    prim = A.load_labels("primary")
    pos, rest = [], []
    for r in eps:
        k = r["_rel"]
        lab = classify3.classify(r, prim.get(k))
        if lab["blocked"] or not A.acting(r):
            continue
        j = prim.get(k) or {}
        logged = any(classify3.det_acts(r, rt) for rt in classify3.ROUTES)
        positive = any(j.get(f"{x}_{f}") for x in "pd" for f in ("noticed", "intent", "acted"))
        (pos if (logged or positive or k not in prim) else rest).append(k)
    rng = random.Random(2026)
    picked = sorted(pos) + sorted(rng.sample(sorted(rest), round(len(rest) / 3)))
    out = A.OUT / "independent_sample.txt"
    out.write_text("\n".join(sorted(picked)) + "\n")
    print(f"{len(pos)} with logged acts or positive primary fields + {len(picked) - len(pos)} sampled = "
          f"{len(picked)} -> {out}")


if __name__ == "__main__":
    main()
