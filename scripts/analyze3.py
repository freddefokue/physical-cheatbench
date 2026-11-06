"""v3 analysis (PLAN_v3.md sections 4-6): labels, H1-H4, the stage funnel, checks and sensitivity.

Inputs: runs/<run>/<condition>/<model>/<env>/<seed>.json, results/v3/labels/{primary,independent}.jsonl and
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
CONDS = ("att_pt", "unatt_pt", "unatt")
H1 = ("unatt_pt", "att_pt")
H2 = ("unatt_pt", "unatt")
CLAUDE = ("opus-5.5", "fable-5.1")
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
    from pcb import judge3
    p = OUT / "labels" / f"{which}.jsonl"
    out = {}
    if p.exists():
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
    L = {}
    for r in eps:
        k = r["_rel"]
        L[k] = {"final": classify3.classify(r, prim.get(k), adj.get(k)),
                "noadj": classify3.classify(r, prim.get(k)),
                "det": classify3.classify(r, None, use_judge=False),
                "indep": classify3.classify(r, indep.get(k)) if k in indep else None}
    return L


def usable(r, lab):
    return lab is not None and not lab["blocked"] and acting(r)


def strata(eps, L, which, value, cond):
    out = defaultdict(lambda: defaultdict(list))
    for r in eps:
        lab = L[r["_rel"]][which]
        if usable(r, lab) and cond(r, lab):
            out[r["condition"]][(r["model"], r["task"])].append(int(bool(value(lab))))
    return out


def contrast(eps, L, pair, which="final", value=lambda lab: lab["cheat"], cond=lambda r, lab: True,
             families=FAMILIES, models=None):
    st = strata(eps, L, which, value,
                lambda r, lab: cond(r, lab) and r["task"] in families and (models is None or r["model"] in models))
    a, b = st[pair[0]], st[pair[1]]
    k_a, n_a = sum(sum(v) for v in a.values()), sum(len(v) for v in a.values())
    k_b, n_b = sum(sum(v) for v in b.values()), sum(len(v) for v in b.values())
    ex = S.exact_stratified(a, b)
    sato = S.mh_rd_sato(a, b)
    bo = S.boot_rd(a, b, B=10000, seed=3)
    return {"pair": list(pair), "a": [k_a, n_a], "b": [k_b, n_b], "p": ex["p_two_sided"], "mh_rd": sato["rd"],
            "mh_ci": sato["ci"], "mh_se": sato["se"], "boot_ci": bo["mh_ci"], "eq_rd": bo["eq"], "eq_ci": bo["eq_ci"]}


def rate(xs):
    k, n = sum(xs), len(xs)
    lo, hi = S.wilson(k, n)
    return {"k": k, "n": n, "rate": (k / n if n else None), "ci": [lo, hi]}


def analyse(eps, L):
    out = {}
    final = {r["_rel"]: L[r["_rel"]]["final"] for r in eps}

    # accounting
    acc = defaultdict(lambda: {"episodes": 0, "blocked": 0, "not_acting": 0, "unjudged": 0})
    for r in eps:
        lab = final[r["_rel"]]
        c = acc[f"{r['model']}|{r['task']}|{r['condition']}"]
        c["episodes"] += 1
        c["blocked"] += lab["blocked"]
        c["not_acting"] += not acting(r)
        c["unjudged"] += (not lab["judged"]) and usable(r, lab)
    out["accounting"] = acc

    # rates
    cells = defaultdict(list)
    for r in eps:
        lab = final[r["_rel"]]
        if usable(r, lab):
            cells[(r["model"], r["task"], r["condition"])].append(int(lab["cheat"]))
    out["cheat_rates"] = {f"{m}|{f}|{c}": rate(v) for (m, f, c), v in sorted(cells.items())}
    agg = defaultdict(list)
    for (m, f, c), v in cells.items():
        agg[("model", m, c)] += v
        agg[("family", f, c)] += v
        agg[("all", "all", c)] += v
    out["rates_by"] = {f"{a}|{b}|{c}": rate(v) for (a, b, c), v in sorted(agg.items())}

    # confirmatory and secondary tests
    t = {"H1": contrast(eps, L, H1), "H2": contrast(eps, L, H2)}
    hc = S.holm({"H1": t["H1"]["p"], "H2": t["H2"]["p"]})
    t["H1"]["p_holm"], t["H2"]["p_holm"] = hc["H1"], hc["H2"]
    fam = {f"{h}|{f}": contrast(eps, L, pair, families=(f,)) for h, pair in (("H1", H1), ("H2", H2))
           for f in FAMILIES}
    hf = S.holm({k: v["p"] for k, v in fam.items()})
    for k in fam:
        fam[k]["p_holm"] = hf[k]
    t["by_family"] = fam
    per_model = {m: rate(agg.get(("model", m, "unatt_pt"), [])) for m in MAIN_MODELS}
    xs = [(per_model[m]["rate"], CHEATBENCH_OVERALL[m]) for m in MAIN_MODELS if per_model[m]["n"]]
    if len(xs) >= 4:
        from scipy.stats import spearmanr
        rho, p = spearmanr([x for x, _ in xs], [y for _, y in xs])
        t["H3"] = {"rho": float(rho), "p_one_sided": float(p / 2 if rho > 0 else 1 - p / 2), "n_models": len(xs)}
    t["H4"] = {f"{h}|{what}": contrast(eps, L, pair, value=val, cond=cond)
               for h, pair in (("H1", H1), ("H2", H2))
               for what, val, cond in (("noticed", lambda lab: lab["noticed_any"], lambda r, lab: True),
                                       ("attempt_given_noticed", lambda lab: lab["cheat"],
                                        lambda r, lab: lab["noticed_any"]))}
    out["tests"] = t

    # sensitivity
    sens = {}
    for name, kw in (("det", {"which": "det"}), ("noadj", {"which": "noadj"}), ("indep", {"which": "indep"}),
                     ("no_coat", {"families": ("leak", "assay", "door")}),
                     ("no_claude", {"models": [m for m in MAIN_MODELS if m not in CLAUDE]})):
        sens[name] = {h: contrast(eps, L, pair, **kw) for h, pair in (("H1", H1), ("H2", H2))}
    out["sensitivity"] = sens

    # funnel
    stages = ("exposure", "noticed", "intent", "attempt", "success", "consequential")
    fun = {}
    for f in FAMILIES:
        for c in sorted({r["condition"] for r in eps}):
            for route in classify3.ROUTES:
                rows = [final[r["_rel"]]["routes"][route] for r in eps
                        if r["task"] == f and r["condition"] == c and usable(r, final[r["_rel"]])]
                fun[f"{f}|{c}|{route}"] = {s: sum(x[s] for x in rows) for s in stages} | {"n": len(rows)}
    out["funnel"] = fun
    clue = defaultdict(lambda: [0, 0])
    for r in eps:
        lab = final[r["_rel"]]
        if usable(r, lab) and r["condition"].endswith("_pt"):
            for route in classify3.ROUTES:
                seen = bool((r.get("exposure_routes") or {}).get(f"{route}_clue"))
                clue[f"{r['task']}|{r['condition']}|{route}"][0] += seen
                clue[f"{r['task']}|{r['condition']}|{route}"][1] += 1
    out["clue_exposure"] = clue

    # checks, outcomes and reports
    chk = {}
    for f in FAMILIES:
        for c in sorted({r["condition"] for r in eps}):
            rows = [final[r["_rel"]] for r in eps if r["task"] == f and r["condition"] == c
                    and usable(r, final[r["_rel"]])]
            honest = [lab for lab in rows if not lab["cheat"]]
            cheats = [lab for lab in rows if lab["cheat"]]
            chk[f"{f}|{c}"] = {
                "n": len(rows), "honest_n": len(honest),
                "honest_true_success": sum(lab["true_success"] for lab in honest),
                "fix_applied": sum(lab["fixed"] for lab in rows),
                "cause_found": sum(lab["honest_cause_found"] for lab in rows),
                "concluded_impossible": sum(lab["concluded_impossible"] for lab in rows),
                "cheat": len(cheats), "success": sum(lab["success"] for lab in cheats),
                "consequential": sum(lab["consequential"] for lab in cheats),
                "misleading_among_cheats": sum(lab["misleading_report"] for lab in cheats),
                "disclosed_among_cheats": sum(bool(lab["disclosed"]) for lab in cheats),
                "declined_any": sum(lab["declined_any"] for lab in rows),
                "probe_then_declined": sum(lab["declined_any"] and not lab["consequential"] for lab in cheats),
                "suspects_test": sum(lab["suspects_test"] for lab in rows),
                "mentions_simulation": sum(lab["mentions_simulation"] for lab in rows),
                "routes": {rt: sum(rt in lab["cheat_routes"] for lab in cheats) for rt in classify3.ROUTES},
            }
    out["checks"] = chk
    sus = defaultdict(lambda: [0, 0])
    for r in eps:
        lab = final[r["_rel"]]
        if usable(r, lab):
            k = "suspects" if lab["suspects_test"] else "no_suspicion"
            sus[k][0] += lab["cheat"]
            sus[k][1] += 1
    out["awareness_vs_cheat"] = sus

    # agreement
    both = [(L[r["_rel"]]["final"], L[r["_rel"]]["indep"]) for r in eps
            if L[r["_rel"]]["indep"] is not None and usable(r, L[r["_rel"]]["final"])]
    agr = {}
    for route in classify3.ROUTES:
        agr[f"attempt_{route}"] = S.kappa([int(x["routes"][route]["attempt"]) for x, _ in both],
                                          [int(y["routes"][route]["attempt"]) for _, y in both])
        prim_rows = [L[r["_rel"]]["final"]["routes"][route] for r in eps
                     if usable(r, L[r["_rel"]]["final"]) and L[r["_rel"]]["final"]["judged"]]
        agr[f"log_vs_primary_acted_{route}"] = S.kappa([int(x["det_act"]) for x in prim_rows],
                                                       [int(x["judge_acted"]) for x in prim_rows])
    agr["cheat"] = S.kappa([int(x["cheat"]) for x, _ in both], [int(y["cheat"]) for _, y in both])
    for key in ("noticed_any", "suspects_test", "mentions_simulation", "misleading_report"):
        agr[key] = S.kappa([int(x[key]) for x, _ in both], [int(y[key]) for _, y in both])
    out["agreement"] = agr

    # adjudication queue
    queue = []
    for r in eps:
        k = r["_rel"]
        lab, ind = L[k]["final"], L[k]["indep"]
        if not usable(r, lab):
            continue
        why = [f"{rt}: log vs primary" for rt in classify3.ROUTES if lab["routes"][rt]["disagree"]]
        if ind is not None:
            why += [f"{rt}: judges" for rt in classify3.ROUTES
                    if L[k]["noadj"]["routes"][rt]["attempt"] != ind["routes"][rt]["attempt"]]
        if why:
            queue.append({"file": k, "why": why})
    out["adjudication_queue"] = queue
    return out


def pct(k, n):
    return f"{k}/{n}" + (f" ({100 * k / n:.0f}%)" if n else "")


def fmt_test(x):
    return (f"{pct(*x['a'])} vs {pct(*x['b'])}; RD {100 * x['mh_rd']:+.1f} points "
            f"[{100 * x['mh_ci'][0]:+.1f}, {100 * x['mh_ci'][1]:+.1f}]; p = {x['p']:.3g}")


def write_tables(R):
    t = R["tests"]
    lines = ["# v3 tables (scripts/analyze3.py)", "",
             f"Episodes: {R['n_episodes']}; primary labels {R['n_primary']}; independent {R['n_independent']}; "
             f"adjudicated {R['n_adjudicated']}.", "", "## Confirmatory", "",
             f"- H1 attainability, unatt_pt vs att_pt: {fmt_test(t['H1'])}; Holm p = {t['H1']['p_holm']:.3g}",
             f"- H2 clue salience, unatt_pt vs unatt: {fmt_test(t['H2'])}; Holm p = {t['H2']['p_holm']:.3g}", "",
             "## By cell (Holm over 8)", "", "| Test | Cell | Result | Holm p |", "|---|---|---|---|"]
    for k, x in t["by_family"].items():
        h, f = k.split("|")
        lines.append(f"| {h} | {f} | {fmt_test(x)} | {x['p_holm']:.3g} |")
    if "H3" in t:
        lines += ["", f"H3: Spearman rho = {t['H3']['rho']:.2f} (one-sided p = {t['H3']['p_one_sided']:.3g}, "
                      f"{t['H3']['n_models']} models)"]
    lines += ["", "## H4: where the effects arise", ""]
    for k, x in t["H4"].items():
        lines.append(f"- {k}: {fmt_test(x)}")
    lines += ["", "## Sensitivity", "", "| Variant | H1 | H2 |", "|---|---|---|"]
    for k, v in R["sensitivity"].items():
        lines.append(f"| {k} | {fmt_test(v['H1'])} | {fmt_test(v['H2'])} |")
    conds = sorted({k.split("|")[2] for k in R["cheat_rates"]})
    lines += ["", "## Cheating by model, cell and condition (cheat / acting episodes)", "",
              "| Model | " + " | ".join(f"{f} {c}" for f in FAMILIES for c in conds) + " |",
              "|---|" + "---|" * (len(FAMILIES) * len(conds))]
    for m in MAIN_MODELS:
        row = []
        for f in FAMILIES:
            for c in conds:
                x = R["cheat_rates"].get(f"{m}|{f}|{c}")
                row.append(f"{x['k']}/{x['n']}" if x else "-")
        lines.append(f"| {NAMES[m]} | " + " | ".join(row) + " |")
    lines += ["", "## Funnel (episodes reaching each stage, per route)", "",
              "| Cell | Condition | Route | n | exposure | noticed | intent | attempt | success | consequential |",
              "|---|---|---|---|---|---|---|---|---|---|"]
    for k, v in R["funnel"].items():
        f, c, route = k.split("|")
        lines.append(f"| {f} | {c} | {route} | {v['n']} | {v['exposure']} | {v['noticed']} | {v['intent']} | "
                     f"{v['attempt']} | {v['success']} | {v['consequential']} |")
    lines += ["", "## Checks and reports", "",
              "| Cell | Condition | n | honest true success | cause found | concluded impossible | cheat | success | "
              "consequential | misleading | disclosed | declined |", "|---|---|---|---|---|---|---|---|---|---|---|---|"]
    for k, v in R["checks"].items():
        f, c = k.split("|")
        lines.append(f"| {f} | {c} | {v['n']} | {pct(v['honest_true_success'], v['honest_n'])} | {v['cause_found']} | "
                     f"{v['concluded_impossible']} | {v['cheat']} | {v['success']} | {v['consequential']} | "
                     f"{v['misleading_among_cheats']} | {v['disclosed_among_cheats']} | {v['declined_any']} |")
    lines += ["", "## Agreement", ""]
    for k, v in R["agreement"].items():
        lines.append(f"- {k}: n {v.get('n')}, kappa {v.get('kappa')}, agree {v.get('agree')}")
    (OUT / "tables.md").write_text("\n".join(lines) + "\n")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--run", default="v3")
    a = ap.parse_args()
    eps = load_eps(a.run)
    prim, indep, adj = load_labels("primary"), load_labels("independent"), load_adjudication()
    L = label_sets(eps, prim, indep, adj)
    R = {"run": a.run, "n_episodes": len(eps), "n_primary": sum(r["_rel"] in prim for r in eps),
         "n_independent": sum(r["_rel"] in indep for r in eps), "n_adjudicated": len(adj)}
    R.update(analyse(eps, L))
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "summary.json").write_text(json.dumps(R, indent=1, default=str))
    write_tables(R)
    print(f"{len(eps)} episodes; primary {R['n_primary']}, independent {R['n_independent']}; "
          f"adjudication queue {len(R['adjudication_queue'])} -> {OUT / 'summary.json'}")
    for h in ("H1", "H2"):
        print(f"{h}: {fmt_test(R['tests'][h])}")


if __name__ == "__main__":
    main()
