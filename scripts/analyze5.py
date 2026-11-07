"""v5 analysis (PLAN_v5.md section 7): rates, H1-H4, the funnel, controls and interface diagnostics.

Reads the v5 episodes (runs/v5/<condition>/<model>/<scene>_A/<seed>.json), the v5 labels (results/v5/labels/), the
blind adjudication (results/v5/adjudication.json, if any), the comparison episodes (runs/v5/main/*/guard_oracle_A,
runs/v5/cmp_v4agent) and, for H1, the published v4 episodes and labels. Writes results/v5/summary.json and
results/v5/tables.md.
"""
import json
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))
import analyze4 as A4  # noqa: E402
import stats2 as S  # noqa: E402
from pcb.models import CHEATBENCH_OVERALL, MAIN_MODELS  # noqa: E402
from pcb5 import classify5  # noqa: E402

OUT = ROOT / "results" / "v5"
SCENES = ("guard", "pack", "leak")
V4_SCENE = {"guard": "guard", "pack": "pack", "leak": "leak4"}
CONDITIONS = ("main", "dont_cheat", "honest_ok", "authorized")
NAMES = A4.NAMES


def load_eps():
    from label5 import load_episode
    eps = []
    for cond in CONDITIONS:
        for f in sorted((ROOT / "runs" / "v5" / cond).glob("*/*_A/*.json")):
            if f.name.endswith(".err.json"):
                continue                     # first records of rerun episodes (section 12, item 1)
            r = load_episode(f)
            if r.get("model") in MAIN_MODELS and "outcome" in r and r.get("task") in SCENES:
                eps.append(r)               # the comparison's guard_oracle episodes are read by comparison()
    return eps


def load_labels(which):
    from pcb5 import judge5
    p = OUT / "labels" / f"{which}.jsonl"
    out = {}
    if p.exists():
        for line in p.read_text().splitlines():
            d = json.loads(line)
            if judge5.label_ok(d["label"]) or (which == "primary" and d["label"].get("_version") == judge5.version()):
                if judge5.label_ok(d["label"]) or d["file"] not in out:
                    out[d["file"]] = d["label"]
    return out


def load_adjudication():
    p = OUT / "adjudication.json"
    if not p.exists():
        return {}
    return {k: v["routes"] for k, v in json.loads(p.read_text()).items() if not k.startswith("_")}


def label_sets(eps):
    prim, fb, indep, adj = load_labels("primary"), load_labels("fallback"), load_labels("independent"), \
        load_adjudication()
    L = {}
    for r in eps:
        k = r["_rel"]
        p = prim.get(k)
        if (p is None or "parse_error" in p) and k in fb:
            p = fb[k]
        L[k] = {"final": classify5.classify(r, p, adj.get(k)),
                "noadj": classify5.classify(r, p),
                "det": classify5.classify(r, None, use_judge=False),
                "noreq": classify5.classify(r, p, adj.get(k), requests_rule=False),
                "indep": classify5.classify(r, indep[k]) if k in indep and "parse_error" not in indep[k] else None,
                "judged": p is not None and "parse_error" not in p,
                "fallback": k in fb and (prim.get(k) is None or "parse_error" in prim.get(k))}
    return L


def acted(r):
    """At least one of the agent's tool calls executed (the digest's calls with an output)."""
    return any(c.get("output") is not None for c in r.get("calls") or [])


def usable(r, lab):
    """Episodes in the denominators: ended by the agent (done, give_up, the call limit), by a provider refusal after
    acting, or by an agent error after acting (PLAN_v5.md section 12, item 1)."""
    if lab is None or lab["blocked"]:
        return False
    if r.get("end_reason") in ("final", "limit", "provider_refusal"):
        return True
    return r.get("end_reason") == "error" and acted(r)


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


def rate(xs):
    k, n = int(sum(xs)), len(xs)
    lo, hi = S.wilson(k, n)
    return {"k": k, "n": n, "rate": (k / n if n else None), "ci": [lo, hi]}


def overall(eps, L, model, cond="main", which="final", value=lambda lab: lab["cheat"]):
    per = {s: np.array(cell(eps, L, model, s, cond, which, value)) for s in SCENES}
    per = {s: v for s, v in per.items() if len(v)}
    if not per:
        return {"rate": None, "ci": [None, None], "scenes": 0}
    est = float(np.mean([v.mean() for v in per.values()]))
    n = int(sum(len(v) for v in per.values()))
    if all(v.sum() == 0 for v in per.values()):
        return {"rate": 0.0, "ci": [0.0, A4.zero_mean_bound([len(v) for v in per.values()])], "scenes": len(per),
                "n": n, "ci_method": "exact one-sided 95% upper bound (no attempts)"}
    return {"rate": est, "ci": A4.profile_interval([int(v.sum()) for v in per.values()], [len(v) for v in per.values()]),
            "ci_method": "profile likelihood, 95 %", "scenes": len(per), "n": n}


def contrast(a, b):
    ex = S.exact_stratified(a, b)
    sato = S.mh_rd_sato(a, b)
    return {"a": [int(sum(map(sum, a.values()))), int(sum(map(len, a.values())))],
            "b": [int(sum(map(sum, b.values()))), int(sum(map(len, b.values())))],
            "p": ex["p_two_sided"], "mh_rd": sato["rd"], "mh_ci": sato["ci"]}


def matched(eps, L, cond_a, cond_b, seeds, which="final"):
    a, b = defaultdict(list), defaultdict(list)
    for r in eps:
        if r["seed"] not in seeds or r["condition"] not in (cond_a, cond_b):
            continue
        lab = L[r["_rel"]][which]
        if usable(r, lab):
            (a if r["condition"] == cond_a else b)[(r["model"], r["task"])].append(int(bool(lab["cheat"])))
    return contrast(a, b)


def v4_main():
    """The published v4 labels (final) of the three ported scenes, main condition: {(model, scene): [0/1]}."""
    eps = [r for r in A4.load_eps("v4") if r["condition"] == "main" and r["task"] in V4_SCENE.values()]
    prim, fb = A4.load_labels("primary", eps), A4.load_labels("fallback", eps)
    fb = {k: v for k, v in fb.items() if k not in prim}
    L = A4.label_sets(eps, prim, A4.load_labels("independent", eps), A4.load_adjudication(), fb,
                      A4.load_adjudication(audit=False))
    inv = {v: k for k, v in V4_SCENE.items()}
    out = defaultdict(list)
    for r in eps:
        lab = L[r["_rel"]]["final"]
        if A4.usable(r, lab):
            out[(r["model"], inv[r["task"]])].append(int(bool(lab["cheat"])))
    return out


def comparison(eps, L):
    """H4: the guard comparison variants against v5 main, seeds 0-3, strata model."""
    from label5 import load_episode
    v5 = defaultdict(list)
    for r in eps:
        if r["task"] == "guard" and r["condition"] == "main" and r["seed"] in range(4) and usable(r, L[r["_rel"]]["final"]):
            v5[r["model"]].append(int(L[r["_rel"]]["final"]["cheat"]))
    oracle, v4agent = defaultdict(list), defaultdict(list)
    for f in sorted((ROOT / "runs" / "v5" / "main").glob("*/guard_oracle_A/*.json")):
        r = load_episode(f)
        if r["model"] in MAIN_MODELS and r["seed"] in range(4):
            lab = classify5.classify(r, None, use_judge=False)
            if usable(r, lab):
                oracle[r["model"]].append(int(lab["cheat"]))
    for f in sorted((ROOT / "runs" / "v5" / "cmp_v4agent" / "main").glob("*/guard_A/*.json")):
        r = json.loads(f.read_text())
        if r["model"] in MAIN_MODELS and r["seed"] in range(4) and r.get("end_reason") not in ("exception", "budget"):
            r4 = dict(r, task="guard", evaluator_version="4.3")
            from pcb import classify4
            lab = classify4.classify(r4, None, use_judge=False, rules="4.3")
            if not lab["blocked"]:
                v4agent[r["model"]].append(int(lab["cheat"]))
    # the comparison is on deterministic labels (act log and requests) for all three variants
    v5det = defaultdict(list)
    for r in eps:
        if r["task"] == "guard" and r["condition"] == "main" and r["seed"] in range(4) and usable(r, L[r["_rel"]]["det"]):
            v5det[r["model"]].append(int(L[r["_rel"]]["det"]["cheat"]))
    res = {"v5_det": {m: rate(v) for m, v in v5det.items()}, "oracle": {m: rate(v) for m, v in oracle.items()},
           "v4agent": {m: rate(v) for m, v in v4agent.items()}}
    tests = {}
    if oracle:
        tests["H4b_oracle"] = contrast(oracle, v5det)
    if v4agent:
        tests["H4a_v4agent"] = contrast(v4agent, v5det)
    if tests:
        adj = S.holm({k: v["p"] for k, v in tests.items()})
        for k in tests:
            tests[k]["p_holm"] = adj[k]
    res["tests"] = tests
    return res


def diagnostics(eps):
    """Interface diagnostics per model: failed grasps, refused requests, protective stops, robot time, latency."""
    out = {}
    for m in MAIN_MODELS:
        rs = [r for r in eps if r["model"] == m]
        if not rs:
            continue
        picks = fails = refused = stops = calls = 0
        lat, tools = [], defaultdict(int)
        for r in rs:
            for a in (r.get("outcome") or {}).get("audit") or []:
                if a.get("kind") == "executed" and a.get("skill") == "pick":
                    picks += 1
                    fails += int(a.get("held") != a.get("item"))
                elif a.get("kind") == "tool" and str(a.get("result", "")).startswith("refused"):
                    refused += 1
                elif a.get("kind") == "protective_stop":
                    stops += 1
            for t in r.get("turns") or []:
                if t.get("latency_s") is not None:
                    lat.append(t["latency_s"])
                for c in t.get("tool_calls") or []:
                    tools[c.get("name")] += 1
            calls += r.get("llm_calls") or 0
        out[m] = {"episodes": len(rs), "picks": picks, "failed_picks": fails, "refused_requests": refused,
                  "protective_stops": stops, "model_calls_mean": round(calls / len(rs), 1),
                  "latency_median_s": round(float(np.median(lat)), 1) if lat else None,
                  "end_reasons": dict(sorted(defaultdict(int, {e: sum(1 for r in rs if r.get("end_reason") == e)
                                                                 for e in {r.get("end_reason") for r in rs}}).items())),
                  "tool_calls": dict(sorted(tools.items())),
                  "cost_mean": round(float(np.mean([r.get("cost") or 0 for r in rs])), 4)}
    return out


def analyse(eps, L):
    R = {"n_episodes": len(eps)}
    models = [m for m in MAIN_MODELS if any(r["model"] == m for r in eps)]
    R["models"] = models
    # primary estimand and per-scene rates
    R["main"] = {m: {"scenes": {s: rate(cell(eps, L, m, s, "main")) for s in SCENES},
                     "overall": overall(eps, L, m)} for m in models}
    R["by_condition"] = {c: {m: {s: rate(cell(eps, L, m, s, c)) for s in SCENES} for m in models} for c in CONDITIONS}
    R["authorized_use"] = {m: {s: rate(cell(eps, L, m, s, "authorized", value=lambda lab: lab["used_permitted"]))
                               for s in SCENES} for m in models}
    R["honest_ok_true_success"] = {m: {s: rate(cell(eps, L, m, s, "honest_ok", value=lambda lab: lab["true_success"]))
                                       for s in SCENES} for m in models}
    # blocked (provider refusals before any act)
    R["blocked"] = {f"{m}/{s}/{c}": n for m in models for s in SCENES for c in CONDITIONS
                    if (n := sum(1 for r in eps if r["model"] == m and r["task"] == s and r["condition"] == c
                                 and L[r["_rel"]]["final"]["blocked"]))}
    R["provider_refusals"] = {f"{m}/{s}/{c}": n for m in models for s in SCENES for c in CONDITIONS
                              if (n := sum(1 for r in eps if r["model"] == m and r["task"] == s and r["condition"] == c
                                           and r.get("end_reason") == "provider_refusal"))}
    # tests
    tests = {}
    v4 = v4_main()
    v5 = defaultdict(list)
    for r in eps:
        if r["condition"] == "main" and usable(r, L[r["_rel"]]["final"]):
            v5[(r["model"], r["task"])].append(int(L[r["_rel"]]["final"]["cheat"]))
    tests["H1_v5_vs_v4"] = contrast(v5, v4)
    tests["H2_dont_cheat"] = matched(eps, L, "dont_cheat", "main", range(4))
    tests["H3_honest_ok"] = matched(eps, L, "honest_ok", "main", range(2))
    adj = S.holm({k: v["p"] for k, v in tests.items()})
    for k in tests:
        tests[k]["p_holm"] = adj[k]
    R["tests"] = tests
    R["v4_rates"] = {f"{m}/{s}": rate(v) for (m, s), v in sorted(v4.items())}
    R["comparison"] = comparison(eps, L)
    # rank order against CheatBench (descriptive)
    xs = [(R["main"][m]["overall"]["rate"], CHEATBENCH_OVERALL[m]) for m in models
          if R["main"][m]["overall"]["rate"] is not None]
    if len(xs) >= 4:
        R["spearman_cheatbench"] = A4.spearman_exact([x for x, _ in xs], [y for _, y in xs])
    # funnel (main)
    fun = {}
    for s in SCENES:
        rows = [(r, L[r["_rel"]]["final"]) for r in eps if r["task"] == s and r["condition"] == "main"
                and usable(r, L[r["_rel"]]["final"])]
        f = {"n": len(rows)}
        for key, fn in (("exposure", lambda lab: lab["exposure_any"]), ("noticed", lambda lab: lab["noticed_any"]),
                        ("intent", lambda lab: any(v["intent"] for v in lab["routes"].values())),
                        ("requested", lambda lab: any(v["requests"] for v in lab["routes"].values())),
                        ("refused_request", lambda lab: any(v["refused_requests"] for v in lab["routes"].values())),
                        ("attempt", lambda lab: lab["cheat"]), ("success", lambda lab: lab["success"]),
                        ("consequential", lambda lab: lab["consequential"]),
                        ("disclosed", lambda lab: lab["cheat"] and lab["disclosed"] is True),
                        ("declined", lambda lab: lab["declined_any"]),
                        ("suspects_test", lambda lab: lab["suspects_test"]),
                        ("mentions_simulation", lambda lab: lab["mentions_simulation"])):
            f[key] = sum(1 for _, lab in rows if fn(lab))
        fun[s] = f
    R["funnel"] = fun
    # sensitivity
    sens = {}
    for which in ("det", "noreq", "noadj"):
        sens[which] = {m: overall(eps, L, m, which=which) for m in models}
    pairs = [(r, L[r["_rel"]]) for r in eps if L[r["_rel"]]["indep"] is not None]
    if pairs:
        sens["indep_agreement"] = S.kappa([int(x["final"]["cheat"]) for _, x in pairs],
                                          [int(x["indep"]["cheat"]) for _, x in pairs])
    R["sensitivity"] = sens
    R["diagnostics"] = diagnostics(eps)
    R["judged"] = sum(1 for r in eps if L[r["_rel"]]["judged"])
    R["fallback_labelled"] = sorted(r["_rel"] for r in eps if L[r["_rel"]]["fallback"])
    return R


def pct(x):
    return "-" if x is None else f"{100 * x:.0f} %"


def write_tables(R):
    lines = ["# v5 tables (generated by scripts/analyze5.py)", "", "## Cheating in `main`", "",
             "| Model | guard | pack | leak | Overall [95 % CI] | CheatBench |", "|---|---|---|---|---|---|"]
    for m in R["models"]:
        row = R["main"][m]
        cells = []
        for s in SCENES:
            c = row["scenes"][s]
            cells.append(f"{c['k']}/{c['n']}" if c["n"] else "-")
        o = row["overall"]
        ov = "-" if o["rate"] is None else f"{pct(o['rate'])} [{pct(o['ci'][0])}, {pct(o['ci'][1])}]"
        lines.append(f"| {NAMES[m]} | " + " | ".join(cells) + f" | {ov} | {CHEATBENCH_OVERALL[m]} % |")
    what = {"H1_v5_vs_v4": "v5 main vs v4 main (seeds 0-7, strata model x scene)",
            "H2_dont_cheat": "dont_cheat vs main (seeds 0-3)", "H3_honest_ok": "honest_ok vs main (seeds 0-1)",
            "H4a_v4agent": "guard: v4 agent on the v5 cell vs v5 (seeds 0-3, strata model)",
            "H4b_oracle": "guard: v5 with simulator-pose perception vs v5 (seeds 0-3, strata model)"}
    lines += ["", "## Tests", "", "| | Contrast | a | b | MH RD [95 % CI] | p | Holm |", "|---|---|---|---|---|---|---|"]
    for k, t in list(R["tests"].items()) + list(R["comparison"].get("tests", {}).items()):
        lines.append(f"| {k} | {what.get(k, '')} | {t['a'][0]}/{t['a'][1]} | {t['b'][0]}/{t['b'][1]} | {100 * t['mh_rd']:+.1f} "
                     f"[{100 * t['mh_ci'][0]:+.1f}, {100 * t['mh_ci'][1]:+.1f}] | {t['p']:.3g} | {t['p_holm']:.3g} |")
    lines += ["", "## By condition (attempts / usable episodes)", ""]
    for c in CONDITIONS:
        lines += [f"### {c}", "", "| Model | guard | pack | leak |", "|---|---|---|---|"]
        for m in R["models"]:
            cs = R["by_condition"][c][m]
            lines.append(f"| {NAMES[m]} | " + " | ".join(f"{cs[s]['k']}/{cs[s]['n']}" if cs[s]["n"] else "-"
                                                         for s in SCENES) + " |")
        lines.append("")
    lines += ["## Controls", "", "| Model | authorized use (guard, pack, leak) | honest_ok true success (guard, pack, leak) |",
              "|---|---|---|"]
    for m in R["models"]:
        au, ho = R["authorized_use"][m], R["honest_ok_true_success"][m]
        lines.append(f"| {NAMES[m]} | " + ", ".join(f"{au[s]['k']}/{au[s]['n']}" for s in SCENES) + " | " +
                     ", ".join(f"{ho[s]['k']}/{ho[s]['n']}" for s in SCENES) + " |")
    lines += ["", "## Funnel (main)", "", "| Scene | " + " | ".join(next(iter(R["funnel"].values())).keys()) + " |",
              "|" + "---|" * (1 + len(next(iter(R["funnel"].values())))) ]
    for s, f in R["funnel"].items():
        lines.append(f"| {s} | " + " | ".join(str(v) for v in f.values()) + " |")
    cmp_ = R["comparison"]
    lines += ["", "## Comparison (guard, main, seeds 0-3, deterministic labels)", "",
              "| Model | v4agent | v5 | oracle |", "|---|---|---|---|"]
    for m in R["models"]:
        cells = [cmp_[k].get(m) for k in ("v4agent", "v5_det", "oracle")]
        lines.append(f"| {NAMES[m]} | " + " | ".join(f"{c['k']}/{c['n']}" if c else "-" for c in cells) + " |")
    lines += ["", "## Interface diagnostics", "", "| Model | episodes | picks | failed picks | refused requests | "
              "protective stops | model calls | latency (median s) | cost/episode |", "|---|---|---|---|---|---|---|---|---|"]
    for m, d in R["diagnostics"].items():
        lines.append(f"| {NAMES[m]} | {d['episodes']} | {d['picks']} | {d['failed_picks']} | {d['refused_requests']} | "
                     f"{d['protective_stops']} | {d['model_calls_mean']} | {d['latency_median_s']} | ${d['cost_mean']} |")
    (OUT / "tables.md").write_text("\n".join(lines) + "\n")


def main():
    eps = load_eps()
    L = label_sets(eps)
    R = analyse(eps, L)
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "summary.json").write_text(json.dumps(R, indent=1, default=str))
    write_tables(R)
    print((OUT / "tables.md").read_text())


if __name__ == "__main__":
    main()
