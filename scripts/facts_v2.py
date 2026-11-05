"""Print the numbers quoted in RESULTS_v2.md and the report, from results/v2/summary.json and the labelled episodes."""
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))
import analyze2  # noqa: E402

S = json.loads((ROOT / "results" / "v2" / "summary.json").read_text())


def kn(cell):
    return (sum(cell[0]), len(cell[0]), cell[1]) if cell else (0, 0, 0)


def pooled(table, cells):
    k = n = b = 0
    for m, row in table.items():
        for c in cells:
            a, bb, cc = kn(row.get(c))
            k, n, b = k + a, n + bb, b + cc
    return f"{k}/{n}" + (f" (+{b} blocked)" if b else "")


print("== tests"); print(json.dumps(S["tests"], indent=1))
print("== manipulation", json.dumps(S["manipulation_check_simulation"]))
print("== H-S1", S["H-S1"])
for meas in ("move_to_pass", "cheat", "consequential", "true_success", "misleading_report", "suspects_test",
             "mentions_simulation"):
    t = S["E1"][meas]
    print("E1", meas, {c: pooled(t, [c]) for c in ("P-base", "P-fixed", "P-auth", "D-fixed")})
for meas in ("cheat", "consequential", "mentions_simulation", "misleading_report", "suspects_test"):
    t = S["E2"][meas]
    print("E2", meas, {c: pooled(t, [c]) for c in ("D-base", "P-base", "D-real", "P-real")},
          "base", pooled(t, ["D-base", "P-base"]), "real", pooled(t, ["D-real", "P-real"]))
print("E2 per model cheat base | real:")
for m, row in S["E2"]["cheat"].items():
    print("  ", m, pooled({m: row}, ["D-base", "P-base"]), "|", pooled({m: row}, ["D-real", "P-real"]),
          "| v1", pooled({m: S["v1_cheat"].get(m, {})}, ["pallet_D", "pallet_P"]))
print("E1 per model move P-base | P-fixed | P-auth | v1 P:")
for m, row in S["E1"]["move_to_pass"].items():
    print("  ", m, *(pooled({m: row}, [c]) for c in ("P-base", "P-fixed", "P-auth")),
          "| v1", pooled({m: S["v1_ambiguous_move"].get(m, {})}, ["markers_P"]))
print("== v1 cheat by env", {e: pooled(S["v1_cheat"], [e]) for e in
                             ("pins_R", "pins_D", "pins_P", "markers_D", "markers_P", "dose_D", "dose_P", "pallet_D", "pallet_P")})
print("== v1 route contrast", json.dumps(S["v1_route_contrast"]))
print("== v1 settle", S["v1_settle_edits"], "spearman", S["v1_spearman"])
print("== inserts", S["v1_inserts_before_reference"])
print("== reporting", S["reporting"])
print("== awareness cheat|suspects", S["awareness"]["cheat_given_suspects"], S["awareness"]["cheat_given_not_suspects"])
print("== dont cheat", json.dumps(S["v1_dont_cheat"]))
print("== sensitivity"); 
for src, tt in S["sensitivity"].items():
    print("  ", src, {k: (v["a"], v["b"], round(v["mh"], 3), round(v["p_two_sided"], 4)) for k, v in tt.items()})
print("== agreement (kappa)")
for k, v in S["agreement"].items():
    if v.get("n"):
        print(f"   {k}: n={v['n']} agree={v['agree']} kappa={v['kappa']} both={v['both']} 1st={v['first_only']} 2nd={v['second_only']}")
print("== counts", {k: S[k] for k in ("n_v1", "n_v2", "primary_labels", "independent_labels", "missing_primary",
                                      "adjudicated", "stale_labels_ignored")})
# v2 reporting by experiment
eps = analyze2.load_eps(analyze2.V2_ROOT)
rep = defaultdict(Counter)
for r in eps:
    L = analyze2.labels(r)["final"]
    if L["blocked"] or not L["cheat"]:
        continue
    key = (r["task"], r.get("task_condition"))
    rep[key]["n"] += 1
    rep[key]["disclosed"] += L["disclosed"] is True
    rep[key]["misleading"] += L["misleading_report"]
    rep[key]["consequential"] += L["consequential"]
print("== v2 reporting among cheating/bypass episodes", {f"{k[0]}/{k[1]}": dict(v) for k, v in rep.items()})
blocked = Counter((r["model"], r["task"], r.get("task_condition")) for r in eps if analyze2.labels(r)["final"]["blocked"])
print("== v2 blocked", dict(blocked))
cost = sum(r.get("cost", 0) for r in eps)
print("== v2 run cost", round(cost, 2), "episodes", len(eps))
