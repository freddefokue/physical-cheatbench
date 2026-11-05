"""v1 episodes for the independent judge (PLAN_v2.md section 5): every non-blocked episode with any positive evidence
(cell records, v1 judge, or v2 primary judge on any act), plus a random 25% of the rest within each environment
(seed 2026). Writes results/v2/independent_sample_v1.txt.
"""
import random
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))
import analyze2  # noqa: E402


def main():
    eps = [r for root in analyze2.V1_ROOTS for r in analyze2.load_eps(root)]
    pos, rest = [], defaultdict(list)
    for r in eps:
        L = analyze2.labels(r)
        if L["final"]["blocked"]:
            continue
        f = L["noadj"]
        any_pos = (any(f["det"].values()) or any((f["judge"] or {}).values())
                   or bool((r.get("label") or {}).get("cheat_attempt")))
        (pos.append if any_pos else rest[(r["env"], r.get("condition"))].append)(r["_rel"])
    rng = random.Random(2026)
    picked = list(pos)
    for k in sorted(rest):
        v = sorted(rest[k])
        picked += rng.sample(v, round(0.25 * len(v)))
    out = analyze2.OUT / "independent_sample_v1.txt"
    out.write_text("\n".join(sorted(picked)) + "\n")
    print(f"{len(pos)} with positive evidence + {len(picked) - len(pos)} sampled negatives = {len(picked)} -> {out}")


if __name__ == "__main__":
    main()
