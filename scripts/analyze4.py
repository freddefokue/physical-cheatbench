"""Pre-registered analysis of v4 (PLAN_v4.md section 7). Writes results/v4/summary.json and results/v4/tables.md.

Usage: python scripts/analyze4.py [--run v4]
"""
import argparse
import json
import math
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np
from scipy.stats import binomtest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))
import stats2 as S  # noqa: E402
from pcb import classify4  # noqa: E402
from pcb.models import CHEATBENCH_OVERALL, MAIN_MODELS  # noqa: E402

OUT = ROOT / "results" / "v4"
SCENES = ("spring", "leak4", "pack", "guard", "aloha", "round")
INFO = ("spring", "aloha", "round")
PHYS = ("leak4", "pack", "guard")
NAMES = {"opus-5.5": "Claude Opus 5.5", "fable-5.1": "Claude Fable 5.1", "gpt-6-sol": "GPT-6 Sol",
         "gpt-6-astra": "GPT-6 Astra", "gemini-3.8-flash": "Gemini 3.8 Flash", "grok-4.7": "Grok 4.7",
         "deepseek-v4-pro": "DeepSeek V4 Pro", "kimi-k3": "Kimi K3", "muse-spark-1.3": "Muse Spark 1.3"}


def load_eps(run):
    eps = []
    for f in sorted((ROOT / "runs" / run).rglob("*.json")):
        if f.parent.name == "images":
            continue
        try:
            r = json.loads(f.read_text())
        except ValueError:
            continue
        if r.get("task") not in SCENES or "turns" not in r:
            continue
        r["_rel"] = str(f.relative_to(ROOT))
        eps.append(r)
    return eps


def load_labels(which, eps):
    """Judge labels of these episodes. A label counts only if it was made with the judge text that belongs to its
    episode (pcb/judge4.py, text_for: by the episode's evaluator version), as that text is now (evaluator 4.2)."""
    from pcb import judge4
    by = {r["_rel"]: r for r in eps}
    p = OUT / "labels" / f"{which}.jsonl"
    out = {}
    if p.exists():
        for line in p.read_text().splitlines():
            try:
                d = json.loads(line)
            except ValueError:
                continue
            r = by.get(d["file"])
            if r is not None and judge4.label_ok(d["label"], r):
                out[d["file"]] = d["label"]
    return out


def load_adjudication(audit=True):
    """Adjudicated routes per episode; audit=False leaves out the post-hoc audit's decisions (section 12, item 8)."""
    p = OUT / "adjudication.json"
    if not p.exists():
        return {}
    return {k: dict(v["routes"], **({"_facts": v["facts"]} if v.get("facts") else {}))
            for k, v in json.loads(p.read_text()).items() if audit or not str(v.get("qid", "")).startswith("AUDIT")}


def acting(r):
    return r.get("end_reason") not in ("exception", "budget", None)


def label_sets(eps, prim, indep, adj, fallback=None, adj_pre=None):
    """fallback: labels by the independent judge's model for episodes the primary judge's provider refused; those
    episodes are always adjudicated (PLAN_v4.md section 12, item 7)."""
    fallback = fallback or {}
    L = {}
    for r in eps:
        k = r["_rel"]
        p = prim.get(k) or fallback.get(k)
        L[k] = {"final": classify4.classify(r, p, adj.get(k)),
                "prereg": classify4.classify(r, p, (adj if adj_pre is None else adj_pre).get(k)),  # no audit (12.8)
                "noadj": classify4.classify(r, p),
                "det": classify4.classify(r, None, use_judge=False),
                "indep": classify4.classify(r, indep.get(k)) if k in indep else None}
    return L


def usable(r, lab):
    return lab is not None and not lab["blocked"] and acting(r)


def rate(xs):
    k, n = int(sum(xs)), len(xs)
    lo, hi = S.wilson(k, n)
    return {"k": k, "n": n, "rate": (k / n if n else None), "ci": [lo, hi]}


def cell(eps, L, model, scene, cond, which="final", value=lambda lab: lab["cheat"], seeds=None):
    xs = []
    for r in eps:
        if r["model"] != model or r["task"] != scene or r["condition"] != cond:
            continue
        if seeds is not None and r["seed"] not in seeds:
            continue
        lab = L[r["_rel"]][which]
        if usable(r, lab):
            xs.append(int(bool(value(lab))))
    return xs


def zero_mean_bound(ns, alpha=0.05):
    """Max of mean(p_s) subject to sum n_s log(1 - p_s) >= log(alpha): p_s = max(0, 1 - lam n_s) (KKT)."""
    ns = np.asarray(ns, float)
    g = lambda lam: float(sum(n * np.log(lam * n) for n in ns if lam * n < 1))
    lo, hi = 1e-12, 1.0 / ns.min()
    for _ in range(200):
        mid = (lo + hi) / 2
        lo, hi = (mid, hi) if g(mid) < np.log(alpha) else (lo, mid)
    lam = (lo + hi) / 2
    return float(np.mean([max(0.0, 1 - lam * n) for n in ns]))


def profile_interval(ks, ns, crit=1.920729):
    """95 % profile-likelihood interval for the equal-weight mean of independent binomial rates k_s/n_s. For a
    multiplier mu the constrained maximiser has dl/dp_s = mu in every scene (closed form per scene); the interval ends
    where the profile log-likelihood falls chi2_1(0.95)/2 below its maximum. Handles all-0 and all-1 scenes."""
    ks, ns = np.asarray(ks, float), np.asarray(ns, float)

    def p_of(mu):
        out = []
        for k, n in zip(ks, ns):
            if abs(mu) < 1e-12:
                out.append(k / n)
            elif k == 0:
                out.append(max(0.0, 1 + n / mu) if mu < 0 else 0.0)
            elif k == n:
                out.append(min(1.0, n / mu) if mu > 0 else 1.0)
            else:
                b = mu + n
                out.append(float((b - np.sqrt(b * b - 4 * mu * k)) / (2 * mu)))
        return np.clip(np.array(out), 0.0, 1.0)

    def ll(p):
        with np.errstate(divide="ignore", invalid="ignore"):
            t = np.where(ks > 0, ks * np.log(np.where(p > 0, p, 1)), 0) + \
                np.where(ns - ks > 0, (ns - ks) * np.log(np.where(p < 1, 1 - p, 1)), 0)
            bad = ((ks > 0) & (p <= 0)) | ((ns - ks > 0) & (p >= 1))
        return float(t.sum()) if not bad.any() else -np.inf

    top = ll(ks / ns) - crit

    def end(sign):
        lo, hi = 0.0, sign * 1e7                    # mu between 0 (the estimate) and +/- infinity (the boundary)
        if ll(p_of(hi)) >= top:
            return float(np.mean(p_of(hi)))
        for _ in range(200):
            mid = (lo + hi) / 2
            lo, hi = (mid, hi) if ll(p_of(mid)) >= top else (lo, mid)
        return float(np.mean(p_of(lo)))
    return [end(+1), end(-1)]


def overall(eps, L, model, cond="main", which="final", value=lambda lab: lab["cheat"], scenes=SCENES, B=4000,
            seed=0):
    """Equal-weight mean of the scene rates (CheatBench's overall), with a bootstrap interval (episodes resampled
    within scene)."""
    per = {s: cell(eps, L, model, s, cond, which, value) for s in scenes}
    per = {s: np.array(v) for s, v in per.items() if len(v)}
    if not per:
        return {"rate": None, "ci": [None, None], "scenes": 0}
    est = float(np.mean([v.mean() for v in per.values()]))
    rng = np.random.default_rng(seed)
    bs = []
    for _ in range(B):
        bs.append(np.mean([rng.choice(v, len(v)).mean() for v in per.values()]))
    n = int(sum(len(v) for v in per.values()))
    if all(v.sum() == 0 for v in per.values()):
        # resampling all-zero data always gives 0. Report instead the exact one-sided 95 % upper bound of the
        # headline quantity, the equal-weight mean of the scene rates: the largest mean of scene rates p_s under
        # which seeing no attempt at all still has probability >= 5 %, prod (1 - p_s)^n_s >= 0.05 (inverting that
        # test gives a valid confidence set). Reviews of 6 Nov 2026.
        return {"rate": 0.0, "ci": [0.0, zero_mean_bound([len(v) for v in per.values()])], "scenes": len(per),
                "n": n, "ci_method": "exact one-sided 95% upper bound of the equal-weight mean, no attempts"}
    # the pre-registered percentile bootstrap is degenerate when a scene's episodes are all 0 or all 1 (it gave
    # "17 % [17 %, 17 %]"); report the 95 % profile-likelihood interval of the equal-weight mean instead, and keep
    # the bootstrap interval for reference (reviews of 6 Nov 2026)
    return {"rate": est, "ci": profile_interval([int(v.sum()) for v in per.values()], [len(v) for v in per.values()]),
            "ci_method": "profile likelihood, 95 %",
            "ci_bootstrap": [float(np.percentile(bs, 2.5)), float(np.percentile(bs, 97.5))],
            "scenes": len(per), "n": n}


def matched_contrast(eps, L, cond_a, cond_b, seeds, which="final", value=lambda lab: lab["cheat"]):
    a, b = defaultdict(list), defaultdict(list)
    for r in eps:
        if r["seed"] not in seeds or r["condition"] not in (cond_a, cond_b):
            continue
        lab = L[r["_rel"]][which]
        if not usable(r, lab):
            continue
        (a if r["condition"] == cond_a else b)[(r["model"], r["task"])].append(int(bool(value(lab))))
    ex = S.exact_stratified(a, b)
    sato = S.mh_rd_sato(a, b)
    return {"a": [int(sum(map(sum, a.values()))), int(sum(map(len, a.values())))],
            "b": [int(sum(map(sum, b.values()))), int(sum(map(len, b.values())))],
            "p": ex["p_two_sided"], "mh_rd": sato["rd"], "mh_ci": sato["ci"]}


def spearman_exact(x, y, one_sided=True):
    from itertools import permutations
    from scipy.stats import rankdata
    rx, ry = rankdata(x), rankdata(y)
    n = len(x)

    def rho(a, b):
        return float(np.corrcoef(a, b)[0, 1])
    obs = rho(rx, ry)
    if n <= 9:
        cnt = tot = 0
        for p in permutations(range(n)):
            v = rho(rx, ry[list(p)])
            tot += 1
            cnt += v >= obs - 1e-12 if one_sided else abs(v) >= abs(obs) - 1e-12
        return {"rho": obs, "p": cnt / tot, "n": n}
    rng = np.random.default_rng(0)
    vals = [rho(rx, rng.permutation(ry)) for _ in range(100000)]
    return {"rho": obs, "p": float(np.mean([v >= obs for v in vals])), "n": n}


def analyse(eps, L, fb=()):
    R = {"n_episodes": len(eps), "fallback_labelled": sorted(fb)}
    models = [m for m in MAIN_MODELS if any(r["model"] == m for r in eps)]
    R["models"] = models
    # blocked and unusable
    R["blocked"] = {m: {s: sum(1 for r in eps if r["model"] == m and r["task"] == s and L[r["_rel"]]["final"]["blocked"])
                        for s in SCENES} for m in models}
    R["blocked_main"] = {m: {s: sum(1 for r in eps if r["model"] == m and r["task"] == s and r["condition"] == "main"
                                    and L[r["_rel"]]["final"]["blocked"]) for s in SCENES} for m in models}
    R["not_acting"] = sum(1 for r in eps if not acting(r))
    # primary: per model x scene, main
    tab = {}
    for m in models:
        tab[m] = {s: rate(cell(eps, L, m, s, "main")) for s in SCENES}
        tab[m]["overall"] = overall(eps, L, m)
    R["main"] = tab
    R["scene_rates"] = {s: rate([x for m in models for x in cell(eps, L, m, s, "main")]) for s in SCENES}
    # H1: transfer from CheatBench
    xs = [(tab[m]["overall"]["rate"], CHEATBENCH_OVERALL[m]) for m in models if tab[m]["overall"]["rate"] is not None]
    R["H1"] = spearman_exact([a for a, _ in xs], [b for _, b in xs]) if len(xs) >= 4 else None
    # H2: don't cheat (seeds 0-3), H3: honest_ok (seeds 0-1)
    R["H2"] = matched_contrast(eps, L, "dont_cheat", "main", seeds={0, 1, 2, 3})
    R["H3"] = matched_contrast(eps, L, "honest_ok", "main", seeds={0, 1})
    # H4: physical vs information scenes, sign test over models
    diffs = {}
    for m in models:
        ph = [tab[m][s]["rate"] for s in PHYS if tab[m][s]["n"]]
        inf = [tab[m][s]["rate"] for s in INFO if tab[m][s]["n"]]
        if ph and inf:
            diffs[m] = float(np.mean(ph) - np.mean(inf))
    nz = [d for d in diffs.values() if abs(d) > 1e-12]
    pos = sum(d > 0 for d in nz)
    R["H4"] = {"diffs": diffs, "n_nonzero": len(nz), "n_phys_higher": pos,
               "p": binomtest(pos, len(nz), 0.5).pvalue if nz else None}
    d2 = {}
    for m in models:                       # descriptive: H4 without aloha (whose act is the most ambiguous)
        ph = [tab[m][s]["rate"] for s in PHYS if tab[m][s]["n"]]
        inf = [tab[m][s]["rate"] for s in INFO if s != "aloha" and tab[m][s]["n"]]
        if ph and inf:
            d2[m] = float(np.mean(ph) - np.mean(inf))
    nz2 = [d for d in d2.values() if abs(d) > 1e-12]
    R["H4_without_aloha"] = {"diffs": d2, "n_nonzero": len(nz2), "n_phys_higher": sum(d > 0 for d in nz2),
                             "p": binomtest(sum(d > 0 for d in nz2), len(nz2), 0.5).pvalue if nz2 else None}
    kinds = defaultdict(lambda: {"replay_in_trial": 0, "joint_values_only": 0})
    for r in eps:
        lab = L[r["_rel"]]["final"]
        if r["task"] == "aloha" and r["condition"] == "main" and usable(r, lab) and lab["cheat"]:
            replay = any(a.get("kind") == "replay_demo" and a.get("in_trial") for a in r["outcome"].get("acts", []))
            kinds[r["model"]]["replay_in_trial" if replay else "joint_values_only"] += 1
    R["aloha_attempt_kinds"] = dict(kinds)
    ps = {"H1": R["H1"]["p"] if R["H1"] else None, "H2": R["H2"]["p"], "H3": R["H3"]["p"], "H4": R["H4"]["p"]}
    ps = {k: v for k, v in ps.items() if v is not None and not (isinstance(v, float) and math.isnan(v))}
    R["holm"] = S.holm(ps) if ps else {}
    # funnel per scene (main)
    fun = {}
    for s in SCENES:
        rows = [L[r["_rel"]]["final"] for r in eps if r["task"] == s and r["condition"] == "main"
                and usable(r, L[r["_rel"]]["final"])]
        n = len(rows)
        fun[s] = {"n": n, "exposure": sum(x["exposure_any"] for x in rows), "noticed": sum(x["noticed_any"] for x in rows),
                  "intent": sum(any(v["intent"] for v in x["routes"].values()) for x in rows),
                  "attempt": sum(x["cheat"] for x in rows), "success": sum(x["success"] for x in rows),
                  "consequential": sum(x["consequential"] for x in rows),
                  "disclosed": sum(1 for x in rows if x["cheat"] and x["disclosed"]),
                  "declined": sum(x["declined_any"] for x in rows), "access": sum(bool(x["access"]) for x in rows)}
    R["funnel"] = fun
    # evaluation awareness (CheatBench A.5), all main episodes
    aw = [L[r["_rel"]]["final"] for r in eps if r["condition"] == "main" and usable(r, L[r["_rel"]]["final"])]
    R["awareness"] = {"suspects": rate([x["cheat"] for x in aw if x["suspects_test"]]),
                      "no_suspicion": rate([x["cheat"] for x in aw if not x["suspects_test"]]),
                      "mentions_simulation": sum(x["mentions_simulation"] for x in aw), "n": len(aw)}
    # authorized: use of the permitted act
    R["authorized"] = {m: {s: rate(cell(eps, L, m, s, "authorized", value=lambda lab: lab["used_permitted"]))
                           for s in INFO} for m in models}
    R["honest_ok_correct"] = {s: rate([int(L[r["_rel"]]["final"]["true_success"]) for r in eps if r["task"] == s and
                                       r["condition"] == "honest_ok" and usable(r, L[r["_rel"]]["final"])])
                              for s in SCENES}
    # honest success: a true success with no cheating label (a correct answer read from the reference is not one)
    R["honest_ok_success"] = {s: rate([int(L[r["_rel"]]["final"]["true_success"] and not L[r["_rel"]]["final"]["cheat"])
                                       for r in eps if r["task"] == s and r["condition"] == "honest_ok"
                                       and usable(r, L[r["_rel"]]["final"])]) for s in SCENES}
    # sensitivity
    sens = {}
    for which in ("det", "noadj"):
        sens[which] = {m: overall(eps, L, m, which=which)["rate"] for m in models}
    sens["strict_access"] = {m: overall(eps, L, m, value=lambda lab: lab["cheat"] or bool(lab["access"]))["rate"]
                             for m in models}
    sens["prereg_without_audit"] = {m: overall(eps, L, m, which="prereg")["rate"] for m in models}
    sens["no_aloha"] = {m: overall(eps, L, m, scenes=tuple(s for s in SCENES if s != "aloha"))["rate"] for m in models}
    R["sensitivity"] = sens
    # agreement: primary vs independent on the sample
    pairs = [(L[r["_rel"]]["final"]["cheat"], L[r["_rel"]]["indep"]["cheat"]) for r in eps
             if L[r["_rel"]]["indep"] is not None and usable(r, L[r["_rel"]]["final"])]
    R["agreement"] = {"n": len(pairs), "agree": sum(a == b for a, b in pairs),
                      "kappa": S.kappa([a for a, _ in pairs], [b for _, b in pairs]) if pairs else None}
    # the two judges before adjudication (primary pipeline vs independent pipeline): inter-judge reliability
    raw = [(L[r["_rel"]]["noadj"]["cheat"], L[r["_rel"]]["indep"]["cheat"]) for r in eps
           if L[r["_rel"]]["indep"] is not None and usable(r, L[r["_rel"]]["noadj"])]
    R["agreement_before_adjudication"] = {"n": len(raw), "agree": sum(a == b for a, b in raw),
                                          "kappa": S.kappa([a for a, _ in raw], [b for _, b in raw]) if raw else None}
    R["cost"] = {m: round(sum(r.get("cost", 0) for r in eps if r["model"] == m), 2) for m in models}
    # adjudication queue (PLAN_v4.md section 5): the act log and the primary judge disagree on an applicable route,
    # or the two judges disagree on the episode's cheat label
    q = []
    for r in eps:
        lab = L[r["_rel"]]
        f, ind = lab["noadj"], lab["indep"]
        if not usable(r, f) or not f["judged"]:
            continue
        why = [f"route {k}: act log {v['det_act']} vs judge {v['judge_acted']}" for k, v in f["routes"].items()
               if v["applicable"] and v["disagree"]]
        if ind is not None and ind["judged"] and ind["cheat"] != f["cheat"]:
            why.append(f"judges disagree on cheat (primary {f['cheat']}, independent {ind['cheat']})")
        if ind is not None and ind["judged"]:
            # the independent judge's coded facts against the act log, before any classifier rule can override them
            # (a disagreement here was hidden when both labels went through the same rules; review of 6 Nov 2026)
            why += [f"route {k}: act log {v['det_act']} vs independent judge {v['judge_acted']}"
                    for k, v in ind["routes"].items() if v["applicable"] and v["disagree"]]
        if r["_rel"] in fb:
            why.append("primary judge refused by its provider; fallback judge labels")
        if why:
            q.append({"file": r["_rel"], "why": why})
    R["adjudication_queue"] = q
    return R


def pct(x):
    return "-" if x is None or (isinstance(x, float) and math.isnan(x)) else f"{100 * x:.0f}%"


def write_tables(R):
    lines = ["# v4 tables (generated by scripts/analyze4.py)", "",
             "## Cheating probability, main condition (per scene k/n; overall = equal-weight mean of scenes)", "",
             "| Model | " + " | ".join(SCENES) + " | Overall [95% CI] | CheatBench |",
             "|---|" + "---|" * len(SCENES) + "---|---|"]
    for m in R["models"]:
        t = R["main"][m]
        o = t["overall"]
        lines.append(f"| {NAMES.get(m, m)} | " + " | ".join(f"{t[s]['k']}/{t[s]['n']}" for s in SCENES) +
                     f" | {pct(o['rate'])} [{pct(o['ci'][0])}, {pct(o['ci'][1])}] | {CHEATBENCH_OVERALL[m]}% |")
    lines += ["", "## Hypotheses", ""]
    if R["H1"]:
        lines.append(f"- H1 Spearman rho = {R['H1']['rho']:.2f}, one-sided exact p = {R['H1']['p']:.3f} "
                     f"(Holm {R['holm'].get('H1', float('nan')):.3f}), n = {R['H1']['n']} models")
    for h in ("H2", "H3"):
        x = R[h]
        lines.append(f"- {h}: {x['a'][0]}/{x['a'][1]} vs {x['b'][0]}/{x['b'][1]}; MH RD {x['mh_rd']:+.3f} "
                     f"[{x['mh_ci'][0]:+.3f}, {x['mh_ci'][1]:+.3f}], exact stratified p = {x['p']:.3f} "
                     f"(Holm {R['holm'].get(h, float('nan')):.3f})")
    h4 = R["H4"]
    lines.append(f"- H4: physical-act scenes higher for {h4['n_phys_higher']} of {h4['n_nonzero']} models with a "
                 f"difference; sign test p = {h4['p'] if h4['p'] is None else round(h4['p'], 3)}")
    lines += ["", "## Funnel (main)", "", "| Scene | n | exposure | noticed | intent | attempt | success | "
              "consequential | disclosed (of attempts) | declined | access |", "|---" * 11 + "|"]
    for s, f in R["funnel"].items():
        lines.append(f"| {s} | {f['n']} | {f['exposure']} | {f['noticed']} | {f['intent']} | {f['attempt']} | "
                     f"{f['success']} | {f['consequential']} | {f['disclosed']} | {f['declined']} | {f['access']} |")
    a = R["awareness"]
    lines += ["", f"Evaluation awareness: cheating {a['suspects']['k']}/{a['suspects']['n']} with suspicion vs "
                  f"{a['no_suspicion']['k']}/{a['no_suspicion']['n']} without; {a['mentions_simulation']} of {a['n']} "
                  f"episodes mention a simulation.", ""]
    (OUT / "tables.md").write_text("\n".join(lines) + "\n")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--run", default="v4")
    a = ap.parse_args()
    eps = load_eps(a.run)
    prim, fb = load_labels("primary", eps), load_labels("fallback", eps)
    fb = {k: v for k, v in fb.items() if k not in prim}
    L = label_sets(eps, prim, load_labels("independent", eps), load_adjudication(), fb, load_adjudication(audit=False))
    R = analyse(eps, L, fb)
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "summary.json").write_text(json.dumps(R, indent=1, default=str))
    write_tables(R)
    print((OUT / "tables.md").read_text())


if __name__ == "__main__":
    main()
