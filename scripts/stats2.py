"""Statistics for the v2 analysis (PLAN_v2.md section 3): exact stratified test, Mantel-Haenszel risk difference with
a consistent stratified bootstrap, Wilson intervals, Cohen's kappa, Holm."""
import math

import numpy as np
from scipy.stats import hypergeom


def wilson(k, n, z=1.96):
    if n == 0:
        return (float("nan"), float("nan"))
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return (max(0.0, c - h), min(1.0, c + h))


def _strata(a, b):
    """a, b: {stratum: list of 0/1}. Keeps strata with at least one episode in each cell."""
    return [(np.asarray(a[s], float), np.asarray(b[s], float)) for s in sorted(set(a) & set(b))
            if len(a[s]) and len(b[s])]


def exact_stratified(a, b):
    """Exact conditional test of equal rates in cells a and b, stratified (exact Cochran-Mantel-Haenszel). The
    statistic is the number of positives in a; under H0 it is a sum of independent hypergeometrics, whose
    distribution is computed exactly by convolution (all permutations within strata). Two-sided p = twice the
    smaller tail, capped at 1."""
    dist = np.array([1.0])
    obs = 0
    for x, y in _strata(a, b):
        n1, n2, t = len(x), len(y), int(x.sum() + y.sum())
        lo, hi = max(0, t - n2), min(n1, t)
        pmf = np.zeros(hi + 1)
        pmf[lo:hi + 1] = hypergeom.pmf(np.arange(lo, hi + 1), n1 + n2, t, n1)
        dist = np.convolve(dist, pmf)
        obs += int(x.sum())
    lower, upper = dist[: obs + 1].sum(), dist[obs:].sum()
    return {"stat": obs, "expected": float((np.arange(len(dist)) * dist).sum()),
            "p_two_sided": float(min(1.0, 2 * min(lower, upper))), "p_lower": float(lower), "p_upper": float(upper)}


def mh_rd(a, b):
    """Mantel-Haenszel pooled risk difference (a minus b), weights n1*n2/(n1+n2)."""
    num = den = 0.0
    for x, y in _strata(a, b):
        w = len(x) * len(y) / (len(x) + len(y))
        num += w * (x.mean() - y.mean())
        den += w
    return num / den if den else float("nan")


def eq_rd(a, b):
    v = [x.mean() - y.mean() for x, y in _strata(a, b)]
    return float(np.mean(v)) if v else float("nan")


def boot_rd(a, b, B=10000, seed=0):
    """Stratified bootstrap (episodes resampled within each stratum x cell) of the MH and equal-weight risk
    differences. Cell sizes are fixed under resampling, so the weights are the same in the estimate and in every
    resample."""
    rng = np.random.default_rng(seed)
    st = _strata(a, b)
    est_mh, est_eq = mh_rd(a, b), eq_rd(a, b)
    if not st:
        return {"mh": est_mh, "eq": est_eq, "mh_ci": [float("nan")] * 2, "eq_ci": [float("nan")] * 2}
    w = np.array([len(x) * len(y) / (len(x) + len(y)) for x, y in st])
    diffs = np.empty((B, len(st)))
    for i, (x, y) in enumerate(st):
        px = rng.binomial(len(x), x.mean(), B) / len(x)
        py = rng.binomial(len(y), y.mean(), B) / len(y)
        diffs[:, i] = px - py
    mh = diffs @ w / w.sum()
    eq = diffs.mean(1)
    return {"mh": float(est_mh), "eq": float(est_eq),
            "mh_ci": [float(np.percentile(mh, 2.5)), float(np.percentile(mh, 97.5))],
            "eq_ci": [float(np.percentile(eq, 2.5)), float(np.percentile(eq, 97.5))]}


def kappa(x, y):
    """Cohen's kappa for two lists of 0/1 labels; also raw agreement and the 2x2 counts."""
    x, y = np.asarray(x, int), np.asarray(y, int)
    n = len(x)
    if n == 0:
        return {"n": 0}
    po = float((x == y).mean())
    pe = float(x.mean() * y.mean() + (1 - x.mean()) * (1 - y.mean()))
    k = (po - pe) / (1 - pe) if pe < 1 else float("nan")
    return {"n": n, "agree": round(po, 4), "kappa": (round(k, 3) if not math.isnan(k) else None),
            "both": int(((x == 1) & (y == 1)).sum()), "first_only": int(((x == 1) & (y == 0)).sum()),
            "second_only": int(((x == 0) & (y == 1)).sum()), "neither": int(((x == 0) & (y == 0)).sum())}


def holm(ps):
    """ps: {name: p}. Holm-adjusted p-values."""
    items = sorted(ps.items(), key=lambda kv: kv[1])
    m, out, run = len(items), {}, 0.0
    for i, (k, p) in enumerate(items):
        run = max(run, min(1.0, (m - i) * p))
        out[k] = run
    return out


def mh_rd_sato(a, b, z=1.959964):
    """Mantel-Haenszel risk difference (a minus b) with Sato's (1989) variance estimator, which stays valid when
    strata are small or sparse (Greenland and Robins 1985 / Sato 1989). Returns rd, se and a Wald interval."""
    num = den = sp = sq = 0.0
    for x, y in _strata(a, b):
        n1, n0 = len(x), len(y)
        x1, x0 = float(x.sum()), float(y.sum())
        N = n1 + n0
        num += (x1 * n0 - x0 * n1) / N
        den += n1 * n0 / N
        sp += (n1 * n1 * x0 - n0 * n0 * x1 + n1 * n0 * (n0 - n1) / 2.0) / (N * N)
        sq += (x1 * (n0 - x0) + x0 * (n1 - x1)) / (2.0 * N)
    if not den:
        return {"rd": float("nan"), "se": float("nan"), "ci": [float("nan")] * 2}
    rd = num / den
    var = max(0.0, (rd * sp + sq) / (den * den))
    se = math.sqrt(var)
    return {"rd": rd, "se": se, "ci": [max(-1.0, rd - z * se), min(1.0, rd + z * se)]}
