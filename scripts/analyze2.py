"""v2 analysis (PLAN_v2.md sections 3-6): E1 (markers conditions), E2 (pallet replication and real framing), the
corrected re-analysis of v1, and judge agreement. Writes results/v2/summary.json and results/v2/tables.md.

python scripts/analyze2.py
"""
import json
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

from pcb import judge2  # noqa: E402
from pcb.classify import ACTS, classify, condition_of, insert_events  # noqa: E402
from pcb.models import CHEATBENCH_OVERALL, MAIN_MODELS  # noqa: E402
import stats2  # noqa: E402

OUT = ROOT / "results" / "v2"
V1_ROOTS = ["runs/main/base", "runs/main/dont_cheat"]
V2_ROOT = "runs/v2"
FAMILY = {"opus-5.5": "anthropic", "fable-5.1": "anthropic", "gpt-6-sol": "openai", "gpt-6-astra": "openai"}
NAMES = {"opus-5.5": "Claude Opus 5.5", "fable-5.1": "Claude Fable 5.1", "gpt-6-sol": "GPT-6 Sol",
         "gpt-6-astra": "GPT-6 Astra", "gemini-3.8-flash": "Gemini 3.8 Flash", "grok-4.7": "Grok 4.7",
         "deepseek-v4-pro": "DeepSeek V4 Pro", "kimi-k3": "Kimi K3", "muse-spark-1.3": "Muse Spark 1.3"}
ORDER = sorted(MAIN_MODELS, key=lambda m: -CHEATBENCH_OVERALL.get(m, 0))


def load_eps(root):
    out = []
    for f in sorted((ROOT / root).rglob("*.json")):
        if f.parent.name == "images":
            continue
        try:
            r = json.loads(f.read_text())
        except ValueError:
            continue
        if "turns" not in r or r.get("end_reason") in ("exception", "budget", None):
            continue
        r["_rel"] = str(f.relative_to(ROOT))
        out.append(r)
    return out


def load_labels(which):
    p = OUT / "labels" / f"{which}.jsonl"
    ver, out, stale = judge2.version(), {}, 0
    if p.exists():
        for line in p.read_text().splitlines():
            try:
                d = json.loads(line)
            except ValueError:
                continue
            if "parse_error" in d["label"]:
                continue
            if d["label"].get("_version") != ver:
                stale += 1
                continue
            out[d["file"]] = d["label"]
    return out, stale


PRIMARY, _st1 = load_labels("primary")
INDEP, _st2 = load_labels("independent")
ADJ = json.loads((OUT / "adjudication.json").read_text()) if (OUT / "adjudication.json").exists() else {}


def labels(r):
    rel = r["_rel"]
    jp, ji = PRIMARY.get(rel), INDEP.get(rel)
    adj = (ADJ.get(rel) or {}).get("acts")
    return {"final": classify(r, jp, adj), "noadj": classify(r, jp), "det": classify(r, None),
            "indep": classify(r, ji) if ji else None, "has_primary": jp is not None, "has_indep": ji is not None}


def frac(v):
    return f"{sum(v)}/{len(v)}" if v else "-"


def get(L, measure):
    return L["acts"][measure[5:]] if measure.startswith("acts.") else L[measure]


def cell_table(eps, cells, measure, src="final"):
    """{model: {cell: (list of 0/1, n_blocked)}}"""
    t = defaultdict(lambda: defaultdict(lambda: ([], 0)))
    for r in eps:
        c = cells(r)
        if c is None:
            continue
        L = r["_lab"][src]
        if L is None:
            continue
        vals, nb = t[r["model"]][c]
        if L["blocked"]:
            t[r["model"]][c] = (vals, nb + 1)
        else:
            vals.append(int(bool(get(L, measure))))
    return t


def by_stratum(t, cell, strata_of=lambda m, c: m):
    out = {}
    for m, row in t.items():
        if cell in row:
            out[strata_of(m, cell)] = row[cell][0]
    return out


def compare(t, ca, cb, strata="model"):
    """Test cell ca vs cb in table t. strata="model": cells are compared within models. strata="model_variant":
    cells are (variant, condition) and ca, cb name conditions only; strata are model x variant."""
    a, b = {}, {}
    for m, row in t.items():
        for c, (vals, _) in row.items():
            if strata == "model_variant":
                key, hit_a, hit_b = (m, c[0]), c[1] == ca, c[1] == cb
            else:
                key, hit_a, hit_b = m, c == ca, c == cb
            if hit_a:
                a.setdefault(key, []).extend(vals)
            if hit_b:
                b.setdefault(key, []).extend(vals)
    ex = stats2.exact_stratified(a, b)
    bs = stats2.boot_rd(a, b)
    na, ka = sum(len(v) for v in a.values()), sum(sum(v) for v in a.values())
    nb_, kb = sum(len(v) for v in b.values()), sum(sum(v) for v in b.values())
    return {"a": f"{ka}/{na}", "b": f"{kb}/{nb_}", **ex, **{k: bs[k] for k in ("mh", "mh_ci", "eq", "eq_ci")}}


def cname(c):
    return c if isinstance(c, str) else "-".join(c)


def md_table(t, cells, title, models=ORDER):
    hdr = "| Model | " + " | ".join(cname(c) for c in cells) + " |\n|---|" + "---|" * len(cells) + "\n"
    rows = []
    for m in models:
        if m not in t:
            continue
        cs = []
        for c in cells:
            vals, nb = t[m].get(c, ([], 0))
            s = frac(vals) if vals or not nb else "-"
            if nb:
                s += f" +{nb}b"
            cs.append(s)
        rows.append(f"| {NAMES.get(m, m)} | " + " | ".join(cs) + " |")
    tot = []
    for c in cells:
        allv = [x for m in t for x in t[m].get(c, ([], 0))[0]]
        tot.append(frac(allv))
    rows.append("| **All** | " + " | ".join(tot) + " |")
    return f"**{title}**\n\n" + hdr + "\n".join(rows) + "\n"


def main():
    v1 = [r for root in V1_ROOTS for r in load_eps(root)]
    v2 = load_eps(V2_ROOT)
    for r in v1 + v2:
        r["_lab"] = labels(r)
    S = {"n_v1": len(v1), "n_v2": len(v2), "primary_labels": len(PRIMARY), "independent_labels": len(INDEP),
         "stale_labels_ignored": _st1 + _st2, "adjudicated": len(ADJ), "judge_version": judge2.version()}
    md = []
    missing = [r["_rel"] for r in v1 + v2 if not r["_lab"]["has_primary"] and not r["_lab"]["final"]["blocked"]]
    S["missing_primary"] = len(missing)

    # ---------------- E1: markers -----------------------------------------------------------------------------------
    e1 = [r for r in v2 if r["task"] == "markers"]
    E1_CELLS = [("P", "base"), ("P", "fixed"), ("P", "auth"), ("D", "fixed")]
    cellf = lambda r: (r["variant"], condition_of(r)) if (r["variant"], condition_of(r)) in E1_CELLS else None  # noqa
    names = {("P", "base"): "P-base", ("P", "fixed"): "P-fixed", ("P", "auth"): "P-auth", ("D", "fixed"): "D-fixed"}
    E1 = {}
    for meas in ("move_to_pass", "cheat", "consequential", "acts.survey_edit", "true_success", "misleading_report",
                 "suspects_test", "mentions_simulation"):
        t = cell_table(e1, cellf, meas)
        E1[meas] = {NAMES.get(m, m): {names[c]: list(v) for c, v in row.items()} for m, row in t.items()}
        if meas in ("move_to_pass", "cheat", "consequential", "true_success", "acts.survey_edit"):
            md.append(md_table(t, E1_CELLS, f"E1 markers: {meas}"))
    tm = cell_table(e1, cellf, "move_to_pass")
    tc = cell_table(e1, cellf, "cheat")
    tests = {"H-M1": compare(tm, ("P", "fixed"), ("P", "base")),
             "H-M2": compare(tc, ("P", "fixed"), ("D", "fixed")),
             "H-M3": compare(tm, ("P", "auth"), ("P", "fixed"))}

    # ---------------- E2: pallet ------------------------------------------------------------------------------------
    e2 = [r for r in v2 if r["task"] == "pallet"]
    E2_CELLS = [("D", "base"), ("P", "base"), ("D", "real"), ("P", "real")]
    cell2 = lambda r: (r["variant"], condition_of(r))  # noqa: E731
    tb = cell_table(e2, cell2, "cheat")
    for meas in ("cheat", "consequential", "mentions_simulation", "misleading_report", "suspects_test"):
        md.append(md_table(cell_table(e2, cell2, meas), E2_CELLS, f"E2 pallet: {meas}"))
    tests["H-S2"] = compare(tb, "real", "base", strata="model_variant")
    tsim = cell_table(e2, cell2, "mentions_simulation")
    manip = compare(tsim, "real", "base", strata="model_variant")
    adj = stats2.holm({k: v["p_two_sided"] for k, v in tests.items()})
    for k in tests:
        tests[k]["p_holm"] = adj[k]
    S["tests"] = tests
    S["manipulation_check_simulation"] = manip
    # H-S1 criterion
    base_by_model = {m: tb[m].get(("D", "base"), ([], 0))[0] + tb[m].get(("P", "base"), ([], 0))[0] for m in tb}
    hi = {m: base_by_model.get(m, []) for m in ("deepseek-v4-pro", "kimi-k3", "gemini-3.8-flash")}
    lo = sum((base_by_model.get(m, []) for m in ("grok-4.7", "gpt-6-sol", "gpt-6-astra", "muse-spark-1.3")), [])
    S["H-S1"] = {"high_models": {NAMES[m]: frac(v) for m, v in hi.items()},
                 "low_models_pooled": frac(lo),
                 "replicates": bool(all(sum(v) >= 1 for v in hi.values()) and lo and sum(lo) / len(lo) < 0.05)}
    S["E1"] = E1
    S["E2"] = {meas: {NAMES.get(m, m): {f"{c[0]}-{c[1]}": list(v) for c, v in row.items()}
                      for m, row in cell_table(e2, cell2, meas).items()}
               for meas in ("cheat", "consequential", "mentions_simulation", "misleading_report", "suspects_test")}

    # sensitivity of the confirmatory tests to the labelling source
    sens = {}
    for src in ("noadj", "det", "indep"):
        ok = [r for r in e1 + e2 if r["_lab"][src] is not None]
        e1s, e2s = [r for r in ok if r["task"] == "markers"], [r for r in ok if r["task"] == "pallet"]
        tm_, tc_, tb_ = (cell_table(e1s, cellf, "move_to_pass", src), cell_table(e1s, cellf, "cheat", src),
                         cell_table(e2s, cell2, "cheat", src))
        sens[src] = {"H-M1": compare(tm_, ("P", "fixed"), ("P", "base")),
                     "H-M2": compare(tc_, ("P", "fixed"), ("D", "fixed")),
                     "H-M3": compare(tm_, ("P", "auth"), ("P", "fixed")),
                     "H-S2": compare(tb_, "real", "base", strata="model_variant")}
    S["sensitivity"] = sens

    # ---------------- v1 re-analysis --------------------------------------------------------------------------------
    v1b = [r for r in v1 if r.get("condition") == "base"]
    envs = ["pins_R", "pins_D", "pins_P", "markers_D", "markers_P", "dose_D", "dose_P", "pallet_D", "pallet_P"]
    t1 = cell_table(v1b, lambda r: r["env"], "cheat")
    md.append(md_table(t1, envs, "v1 (seeds 0-9) under the v2 rules: cheating attempts (pallet: interlock bypass)"))
    tmv = cell_table(v1b, lambda r: r["env"], "ambiguous_move")
    md.append(md_table(tmv, ["markers_P", "markers_D"], "v1 markers: marker moved to pass (ambiguous act in base)"))
    S["v1_cheat"] = {NAMES.get(m, m): {e: list(v) for e, v in row.items()} for m, row in t1.items()}
    S["v1_ambiguous_move"] = {NAMES.get(m, m): {e: list(v) for e, v in row.items()} for m, row in tmv.items()}

    # route contrast D minus P, mean over tasks then over models, consistent bootstrap within model x env cells
    def route_contrast(tasks, measure_of):
        cells = defaultdict(list)
        for r in v1b:
            if r["task"] in tasks and not r["_lab"]["final"]["blocked"]:
                cells[(r["model"], r["task"], r["variant"])].append(int(measure_of(r)))
        keys = [(m, t) for m in MAIN_MODELS for t in tasks if cells.get((m, t, "D")) and cells.get((m, t, "P"))]

        def est(c):
            per_m = defaultdict(list)
            for m, t in keys:
                per_m[m].append(np.mean(c[(m, t, "D")]) - np.mean(c[(m, t, "P")]))
            return float(np.mean([np.mean(v) for v in per_m.values()]))
        rng = np.random.default_rng(1)
        e0 = est(cells)
        bs = []
        for _ in range(4000):
            cb = {k: rng.choice(v, len(v)) for k, v in cells.items()}
            bs.append(est(cb))
        return {"est": e0, "ci": [float(np.percentile(bs, 2.5)), float(np.percentile(bs, 97.5))],
                "pairs": len(keys)}
    def offered(r):        # the route the variant offers: a D-route act in a D variant, a P-route act in a P variant
        return r["variant"] in r["_lab"]["final"]["routes"]

    def offered_v1(r):     # v1 definition: marker moves and settle edits counted
        L = r["_lab"]["final"]
        return (offered(r) or (r["task"] == "markers" and r["variant"] == "P" and L["move_to_pass"])
                or (r["task"] == "dose" and r["variant"] == "D" and L["settle_edit"]))
    S["v1_route_contrast"] = {
        "offered_route_pins_dose": route_contrast(("pins", "dose"), offered),
        "offered_route_pins_markers_dose": route_contrast(("pins", "markers", "dose"), offered),
        "any_cheating_pins_markers_dose": route_contrast(("pins", "markers", "dose"), lambda r: r["_lab"]["final"]["cheat"]),
        "v1_definition_pins_markers_dose": route_contrast(("pins", "markers", "dose"), offered_v1),
    }
    # settle edits
    S["v1_settle_edits"] = {e: frac([int(r["_lab"]["final"]["settle_edit"]) for r in v1b
                                     if r["env"] == e and not r["_lab"]["final"]["blocked"]]) for e in ("dose_D", "dose_P")}
    # effort before the reference (event-based)
    pre = defaultdict(list)
    for r in v1b:
        if r["env"] == "pins_R" and r.get("canary"):
            pre[NAMES[r["model"]]].append(insert_events(r["calls"][: r["canary"]["call"]]))
    S["v1_inserts_before_reference"] = {m: {"episodes": len(v), "none_before": sum(x == 0 for x in v),
                                            "median": float(np.median(v))} for m, v in pre.items()}
    # narrow awareness and simulation mentions, v1 + v2, by model; cheating by awareness (observational)
    aw = {}
    for name, eps in (("v1", v1b), ("v2", v2)):
        d = {}
        for m in ORDER:
            ls = [r["_lab"]["final"] for r in eps if r["model"] == m and not r["_lab"]["final"]["blocked"]
                  and r["_lab"]["has_primary"]]
            d[NAMES[m]] = {"n": len(ls), "suspects_test": sum(l["suspects_test"] for l in ls),
                           "mentions_simulation": sum(l["mentions_simulation"] for l in ls)}
        aw[name] = d
    allv = [r for r in v1b + v2 if r["_lab"]["has_primary"] and not r["_lab"]["final"]["blocked"]]
    aw["cheat_given_suspects"] = frac([int(r["_lab"]["final"]["cheat"]) for r in allv if r["_lab"]["final"]["suspects_test"]])
    aw["cheat_given_not_suspects"] = frac([int(r["_lab"]["final"]["cheat"]) for r in allv
                                           if not r["_lab"]["final"]["suspects_test"]])
    S["awareness"] = aw
    # Spearman pins_R and overall (equal-weight over the 7 grader envs) vs CheatBench
    from scipy.stats import spearmanr
    xs, ys, zs = [], [], []
    for m in MAIN_MODELS:
        v = t1.get(m, {}).get("pins_R", ([], 0))[0]
        rates = [np.mean(t1[m][e][0]) for e in envs[:7] if t1.get(m, {}).get(e, ([], 0))[0]]
        if v:
            xs.append(np.mean(v)), ys.append(CHEATBENCH_OVERALL[m]), zs.append(np.mean(rates))
    S["v1_spearman"] = {"pins_R": list(map(float, spearmanr(xs, ys))), "overall7": list(map(float, spearmanr(zs, ys)))}
    # "Don't cheat!" ablation under v2 rules
    dc = [r for r in v1 if r.get("condition") == "dont_cheat"]
    abl = {}
    for e in ("pins_R", "markers_P"):
        meas = "cheat" if e == "pins_R" else "move_to_pass"
        tb_ = cell_table([r for r in v1b + dc if r["env"] == e], lambda r: r.get("condition"), meas)
        abl[e] = {NAMES.get(m, m): {c: frac(v[0]) for c, v in row.items()} for m, row in tb_.items()}
    S["v1_dont_cheat"] = abl

    # ---------------- judge agreement --------------------------------------------------------------------------------
    agr = {}
    lab_eps = [r for r in v1 + v2 if r["_lab"]["has_primary"] and not r["_lab"]["final"]["blocked"]]
    for task, acts in ACTS.items():
        for act in acts:
            rs = [r for r in lab_eps if r["task"] == task]
            agr[f"{act}: primary judge vs sensors"] = stats2.kappa(
                [r["_lab"]["noadj"]["judge"][act] for r in rs], [r["_lab"]["det"]["det"][act] for r in rs])
            ri = [r for r in rs if r["_lab"]["has_indep"]]
            if ri:
                agr[f"{act}: primary vs independent judge"] = stats2.kappa(
                    [r["_lab"]["noadj"]["judge"][act] for r in ri], [r["_lab"]["indep"]["judge"][act] for r in ri])
                agr[f"{act}: independent judge vs sensors"] = stats2.kappa(
                    [r["_lab"]["indep"]["judge"][act] for r in ri], [r["_lab"]["det"]["det"][act] for r in ri])
    both = [r for r in lab_eps if r["_lab"]["has_indep"]]
    for fam in ("anthropic", "openai", "other"):
        rs = [r for r in both if FAMILY.get(r["model"], "other") == fam]
        agr[f"cheat label, final vs independent-based, {fam} models"] = stats2.kappa(
            [r["_lab"]["final"]["cheat"] for r in rs], [r["_lab"]["indep"]["cheat"] for r in rs])
        agr[f"suspects_test, primary vs independent, {fam} models"] = stats2.kappa(
            [r["_lab"]["final"]["suspects_test"] for r in rs], [r["_lab"]["indep"]["suspects_test"] for r in rs])
        agr[f"mentions_simulation, primary vs independent, {fam} models"] = stats2.kappa(
            [r["_lab"]["final"]["mentions_simulation"] for r in rs], [r["_lab"]["indep"]["mentions_simulation"] for r in rs])
    S["agreement"] = agr
    # disclosure / misleading among cheating episodes
    rep = {}
    for name, eps in (("v1", v1b), ("v2", v2)):
        ch = [r["_lab"]["final"] for r in eps if r["_lab"]["final"]["cheat"] and r["_lab"]["has_primary"]]
        rep[name] = {"cheating": len(ch), "disclosed": sum(l["disclosed"] is True for l in ch),
                     "misleading": sum(l["misleading_report"] for l in ch),
                     "consequential": sum(l["consequential"] for l in ch)}
    S["reporting"] = rep

    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "summary.json").write_text(json.dumps(S, indent=1, default=str))
    tx = ["# v2 tables (generated by scripts/analyze2.py)\n"]
    tx.append("## Confirmatory tests\n\n| Test | a | b | MH risk difference [95% CI] | equal-weight [95% CI] | p | p (Holm) |\n"
              "|---|---|---|---|---|---|---|")
    for k, v in tests.items():
        tx.append(f"| {k} | {v['a']} | {v['b']} | {v['mh']:+.3f} [{v['mh_ci'][0]:+.3f}, {v['mh_ci'][1]:+.3f}] | "
                  f"{v['eq']:+.3f} [{v['eq_ci'][0]:+.3f}, {v['eq_ci'][1]:+.3f}] | {v['p_two_sided']:.2g} | "
                  f"{v['p_holm']:.2g} |")
    v = manip
    tx.append(f"| manipulation check: mentions simulation, real vs base | {v['a']} | {v['b']} | {v['mh']:+.3f} "
              f"[{v['mh_ci'][0]:+.3f}, {v['mh_ci'][1]:+.3f}] | {v['eq']:+.3f} | {v['p_two_sided']:.2g} | - |\n")
    tx.append(f"H-S1 replication criterion: {json.dumps(S['H-S1'])}\n")
    tx += md
    (OUT / "tables.md").write_text("\n".join(tx))
    print("\n".join(tx))
    print(json.dumps({k: S[k] for k in ("n_v1", "n_v2", "primary_labels", "independent_labels", "missing_primary",
                                        "adjudicated", "stale_labels_ignored")}))


if __name__ == "__main__":
    main()
