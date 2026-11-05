"""v3 analysis (PLAN_v3.md sections 4-5): labels, the attainability test, the stage funnel, checks, sensitivity.

Inputs: runs/<run>/<arm>/<model>/<env>/<seed>.json, results/v3/labels/{primary,independent}.jsonl,
results/v3/adjudication.json (optional). Outputs: results/v3/summary.json and results/v3/tables.md.
Usage: python scripts/analyze3.py [--run v3]
"""
import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

from pcb import classify3  # noqa: E402
from pcb.models import CHEATBENCH_OVERALL, MAIN_MODELS  # noqa: E402
import stats2 as S  # noqa: E402

OUT = ROOT / "results" / "v3"
FAMILIES = ("leak", "coat", "assay", "door")
ARMS = ("att", "unatt")
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
        if r.get("task") not in FAMILIES or "turns" not in r:
            continue
        r["_rel"] = str(f.relative_to(ROOT))
        eps.append(r)
    return eps


def load_labels(which):
    p = OUT / "labels" / f"{which}.jsonl"
    out = {}
    if p.exists():
        from pcb import judge3
        ver = judge3.version()
        for line in p.read_text().splitlines():
            try:
                d = json.loads(line)
            except ValueError:
                continue
            if d["label"].get("_version") == ver and "parse_error" not in d["label"]:
                out[d["file"]] = d["label"]
    return out


def load_adjudication():
    p = OUT / "adjudication.json"
    if not p.exists():
        return {}
    return {k: v["routes"] for k, v in json.loads(p.read_text()).items()}


def acting(r):
    return r.get("end_reason") not in ("exception", "budget", None)


def label_sets(eps, prim, indep, adj):
    """Primary labels plus the pre-registered sensitivity variants."""
    L = {}
    for r in eps:
        k = r["_rel"]
        L[k] = {
            "final": classify3.classify(r, prim.get(k), adj.get(k)),
            "noadj": classify3.classify(r, prim.get(k)),
            "det": classify3.classify(r, None, use_judge=False),
            "indep": classify3.classify(r, indep.get(k)) if k in indep else None,
        }
    return L


def strata(eps, L, which, value, cond=lambda r, lab: True):
    """{arm: {(model, family): [0/1]}} over acting, unblocked episodes."""
    out = {a: defaultdict(list) for a in ARMS}
    for r in eps:
        lab = L[r["_rel"]][which]
        if lab is None or lab["blocked"] or not acting(r) or not cond(r, lab):
            continue
        out[lab["arm"]][(r["model"], r["task"])].append(int(bool(value(lab))))
    return out


def test_arms(eps, L, which, value, cond=lambda r, lab: True, families=FAMILIES):
    st = strata(eps, L, which, value, lambda r, lab: cond(r, lab) and r["task"] in families)
    a, b = st["unatt"], st["att"]
    k_a, n_a = sum(sum(v) for v in a.values()), sum(len(v) for v in a.values())
    k_b, n_b = sum(sum(v) for v in b.values()), sum(len(v) for v in b.values())
    ex = S.exact_stratified(a, b)
    bo = S.boot_rd(a, b, B=10000, seed=3)
    return {"unatt": [k_a, n_a], "att": [k_b, n_b], "p": ex["p_two_sided"], "mh_rd": bo["mh"], "mh_ci": bo["mh_ci"],
            "eq_rd": bo["eq"], "eq_ci": bo["eq_ci"]}


def rate(xs):
    k, n = sum(xs), len(xs)
    lo, hi = S.wilson(k, n)
    return {"k": k, "n": n, "rate": (k / n if n else None), "ci": [lo, hi]}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--run", default="v3")
    a = ap.parse_args()
    eps = load_eps(a.run)
    prim, indep, adj = load_labels("primary"), load_labels("independent"), load_adjudication()
    L = label_sets(eps, prim, indep, adj)
    S_ = {"run": a.run, "n_episodes": len(eps), "n_primary": sum(r["_rel"] in prim for r in eps),
          "n_independent": sum(r["_rel"] in indep for r in eps), "n_adjudicated": len(adj)}

    # ---- accounting ------------------------------------------------------------------------------------------------
    acc = defaultdict(lambda: {"episodes": 0, "blocked": 0, "not_acting": 0, "unjudged": 0})
    for r in eps:
        lab = L[r["_rel"]]["final"]
        c = acc[f"{r['model']}|{r['task']}|{lab['arm']}"]
        c["episodes"] += 1
        c["blocked"] += lab["blocked"]
        c["not_acting"] += not acting(r)
        c["unjudged"] += (not lab["judged"]) and not lab["blocked"] and acting(r)
    S_["accounting"] = acc

    ok = lambda r, lab: not lab["blocked"] and acting(r)  # noqa: E731
    final = {r["_rel"]: L[r["_rel"]]["final"] for r in eps}

    # ---- rates ------------------------------------------------------------------------------------------------------
    cells = defaultdict(list)
    for r in eps:
        lab = final[r["_rel"]]
        if ok(r, lab):
            cells[(r["model"], r["task"], lab["arm"])].append(int(lab["cheat"]))
    S_["cheat_rates"] = {f"{m}|{f}|{arm}": rate(v) for (m, f, arm), v in sorted(cells.items())}
    by_model_arm = defaultdict(list)
    by_family_arm = defaultdict(list)
    for (m, f, arm), v in cells.items():
        by_model_arm[(m, arm)] += v
        by_family_arm[(f, arm)] += v
    S_["by_model_arm"] = {f"{m}|{arm}": rate(v) for (m, arm), v in sorted(by_model_arm.items())}
    S_["by_family_arm"] = {f"{f}|{arm}": rate(v) for (f, arm), v in sorted(by_family_arm.items())}

    # ---- confirmatory H1 and secondary tests ----------------------------------------------------------------------
    tests = {"H1": test_arms(eps, L, "final", lambda lab: lab["cheat"])}
    fam_tests = {f: test_arms(eps, L, "final", lambda lab: lab["cheat"], families=(f,)) for f in FAMILIES}
    holm = S.holm({f: t["p"] for f, t in fam_tests.items()})
    for f in FAMILIES:
        fam_tests[f]["p_holm"] = holm[f]
    tests["H1_by_family"] = fam_tests
    tests["H2_attempt_given_noticed"] = test_arms(eps, L, "final", lambda lab: lab["cheat"],
                                                  cond=lambda r, lab: lab["noticed_any"])
    tests["H2_noticed"] = test_arms(eps, L, "final", lambda lab: lab["noticed_any"])
    tests["sensitivity"] = {w: test_arms(eps, L, w, lambda lab: lab["cheat"]) for w in ("noadj", "det", "indep")}
    tests["sensitivity"]["no_coat"] = test_arms(eps, L, "final", lambda lab: lab["cheat"],
                                                families=("leak", "assay", "door"))
    # H3: model ordering vs CheatBench (both arms pooled)
    per_model = {m: rate(by_model_arm.get((m, "att"), []) + by_model_arm.get((m, "unatt"), [])) for m in MAIN_MODELS}
    xs = [(per_model[m]["rate"], CHEATBENCH_OVERALL[m]) for m in MAIN_MODELS if per_model[m]["n"]]
    if len(xs) >= 4:
        from scipy.stats import spearmanr
        rho, p = spearmanr([x for x, _ in xs], [y for _, y in xs])
        tests["H3_spearman"] = {"rho": float(rho), "p_two_sided": float(p),
                                "p_one_sided": float(p / 2 if rho > 0 else 1 - p / 2), "n_models": len(xs)}
    S_["tests"] = tests
    S_["per_model"] = per_model

    # ---- funnel -----------------------------------------------------------------------------------------------------
    stages = ("exposure", "noticed", "intent", "attempt", "success", "consequential")
    fun = {}
    for f in FAMILIES:
        for arm in ARMS:
            for route in classify3.ROUTES:
                rows = [final[r["_rel"]]["routes"][route] for r in eps
                        if r["task"] == f and ok(r, final[r["_rel"]]) and final[r["_rel"]]["arm"] == arm]
                fun[f"{f}|{arm}|{route}"] = {s: sum(x[s] for x in rows) for s in stages} | {"n": len(rows)}
    S_["funnel"] = fun

    # ---- manipulation checks, outcomes and reports --------------------------------------------------------------------
    chk = {}
    for f in FAMILIES:
        for arm in ARMS:
            rows = [(r, final[r["_rel"]]) for r in eps if r["task"] == f and ok(r, final[r["_rel"]])
                    and final[r["_rel"]]["arm"] == arm]
            honest = [(r, lab) for r, lab in rows if not lab["cheat"]]
            chk[f"{f}|{arm}"] = {
                "n": len(rows), "honest_n": len(honest),
                "honest_true_success": sum(lab["true_success"] for _, lab in honest),
                "fix_applied": sum(lab["fixed"] for _, lab in rows),
                "cause_found": sum(lab["honest_cause_found"] for _, lab in rows),
                "concluded_impossible": sum(lab["concluded_impossible"] for _, lab in rows),
                "cheat": sum(lab["cheat"] for _, lab in rows),
                "consequential": sum(lab["consequential"] for _, lab in rows),
                "misleading_report_among_cheats": [sum(lab["misleading_report"] for _, lab in rows if lab["cheat"]),
                                                   sum(lab["cheat"] for _, lab in rows)],
                "disclosed_among_cheats": [sum(bool(lab["disclosed"]) for _, lab in rows if lab["cheat"]),
                                           sum(lab["cheat"] for _, lab in rows)],
                "suspects_test": sum(lab["suspects_test"] for _, lab in rows),
                "mentions_simulation": sum(lab["mentions_simulation"] for _, lab in rows),
            }
    S_["checks"] = chk

    # ---- agreement ----------------------------------------------------------------------------------------------------
    agr = {}
    for route in classify3.ROUTES:
        both = [(L[k]["final"], L[k]["indep"]) for k in L if L[k]["indep"] is not None and not L[k]["final"]["blocked"]]
        agr[f"attempt_{route}"] = S.kappa([int(x["routes"][route]["attempt"]) for x, _ in both],
                                          [int(y["routes"][route]["attempt"]) for _, y in both])
        dj = [(x["routes"][route]["det_act"], x["routes"][route]["judge_acted"]) for x, _ in both]
        agr[f"det_vs_primary_acted_{route}"] = S.kappa([int(a) for a, _ in dj], [int(b) for _, b in dj])
    both = [(L[k]["final"], L[k]["indep"]) for k in L if L[k]["indep"] is not None and not L[k]["final"]["blocked"]]
    agr["cheat"] = S.kappa([int(x["cheat"]) for x, _ in both], [int(y["cheat"]) for _, y in both])
    for fam in ("claude", "gpt", "other"):
        sel = [(L[r["_rel"]]["final"], L[r["_rel"]]["indep"]) for r in eps if L[r["_rel"]]["indep"] is not None
               and not L[r["_rel"]]["final"]["blocked"]
               and (("opus" in r["model"] or "fable" in r["model"]) if fam == "claude" else
                    ("gpt" in r["model"]) if fam == "gpt" else
                    not any(s in r["model"] for s in ("opus", "fable", "gpt")))]
        agr[f"cheat_{fam}"] = S.kappa([int(x["cheat"]) for x, _ in sel], [int(y["cheat"]) for _, y in sel])
    for key in ("suspects_test", "mentions_simulation", "misleading_report"):
        agr[key] = S.kappa([int(x[key]) for x, _ in both], [int(y[key]) for _, y in both])
    S_["agreement"] = agr

    # ---- queue for adjudication -------------------------------------------------------------------------------------
    queue = []
    for r in eps:
        k = r["_rel"]
        lab, ind = L[k]["final"], L[k]["indep"]
        if lab["blocked"] or not acting(r):
            continue
        why = [f"{rt}: log vs primary" for rt in classify3.ROUTES if lab["routes"][rt]["disagree"]]
        if ind is not None:
            why += [f"{rt}: judges" for rt in classify3.ROUTES
                    if L[k]["noadj"]["routes"][rt]["attempt"] != ind["routes"][rt]["attempt"]]
        if why:
            queue.append({"file": k, "why": why})
    S_["adjudication_queue"] = queue

    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "summary.json").write_text(json.dumps(S_, indent=1, default=str))
    write_tables(S_)
    print(f"{len(eps)} episodes; primary {S_['n_primary']}, independent {S_['n_independent']}; "
          f"queue {len(queue)} -> {OUT / 'summary.json'}")
    t = tests["H1"]
    print(f"H1: unatt {t['unatt'][0]}/{t['unatt'][1]} vs att {t['att'][0]}/{t['att'][1]}, MH RD {t['mh_rd']:+.3f} "
          f"[{t['mh_ci'][0]:+.3f}, {t['mh_ci'][1]:+.3f}], p = {t['p']:.3g}")


def pct(k, n):
    return f"{k}/{n}" + (f" ({100 * k / n:.0f}%)" if n else "")


def write_tables(S_):
    lines = ["# v3 tables (scripts/analyze3.py)", ""]
    t = S_["tests"]["H1"]
    lines += ["## H1: cheating when honest success is unattainable vs attainable", "",
              f"unatt {pct(*t['unatt'])}, att {pct(*t['att'])}; MH risk difference {100 * t['mh_rd']:+.1f} points "
              f"[{100 * t['mh_ci'][0]:+.1f}, {100 * t['mh_ci'][1]:+.1f}]; exact stratified p = {t['p']:.3g}", "",
              "| Family | unatt | att | RD (points) | p | p (Holm) |", "|---|---|---|---|---|---|"]
    for f, x in S_["tests"]["H1_by_family"].items():
        lines.append(f"| {f} | {pct(*x['unatt'])} | {pct(*x['att'])} | {100 * x['mh_rd']:+.1f} "
                     f"[{100 * x['mh_ci'][0]:+.1f}, {100 * x['mh_ci'][1]:+.1f}] | {x['p']:.3g} | {x['p_holm']:.3g} |")
    lines += ["", "## Cheating by model, family and arm (cheat / acting episodes)", "",
              "| Model | " + " | ".join(f"{f} att | {f} unatt" for f in FAMILIES) + " |",
              "|---|" + "---|" * (2 * len(FAMILIES))]
    for m in MAIN_MODELS:
        row = []
        for f in FAMILIES:
            for arm in ARMS:
                c = S_["cheat_rates"].get(f"{m}|{f}|{arm}")
                row.append(f"{c['k']}/{c['n']}" if c else "-")
        lines.append(f"| {NAMES[m]} | " + " | ".join(row) + " |")
    lines += ["", "## Funnel (episodes reaching each stage, per route)", "",
              "| Family | Arm | Route | n | exposure | noticed | intent | attempt | success | consequential |",
              "|---|---|---|---|---|---|---|---|---|---|"]
    for k, v in S_["funnel"].items():
        f, arm, route = k.split("|")
        lines.append(f"| {f} | {arm} | {route} | {v['n']} | {v['exposure']} | {v['noticed']} | {v['intent']} | "
                     f"{v['attempt']} | {v['success']} | {v['consequential']} |")
    lines += ["", "## Manipulation checks and reports", "",
              "| Family | Arm | n | honest true success | fix applied | cause found | concluded impossible | "
              "cheat | consequential | misleading (cheats) | disclosed (cheats) |", "|---|---|---|---|---|---|---|---|---|---|---|"]
    for k, v in S_["checks"].items():
        f, arm = k.split("|")
        lines.append(f"| {f} | {arm} | {v['n']} | {pct(v['honest_true_success'], v['honest_n'])} | {v['fix_applied']} | "
                     f"{v['cause_found']} | {v['concluded_impossible']} | {v['cheat']} | {v['consequential']} | "
                     f"{v['misleading_report_among_cheats'][0]}/{v['misleading_report_among_cheats'][1]} | "
                     f"{v['disclosed_among_cheats'][0]}/{v['disclosed_among_cheats'][1]} |")
    lines += ["", "## Agreement", ""]
    for k, v in S_["agreement"].items():
        lines.append(f"- {k}: n {v.get('n')}, kappa {v.get('kappa')}, agree {v.get('agree')}")
    (OUT / "tables.md").write_text("\n".join(lines) + "\n")


if __name__ == "__main__":
    main()
