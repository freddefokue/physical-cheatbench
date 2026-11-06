"""Validates the repaired classifier rules (evaluator 4.1, or 4.2) on the published v4 episodes.

Runs pcb/classify4.py with rules "4.1" (or --rules 4.2) and the primary judge's labels but NO adjudication, and compares the result with
the final labels (rules 4.0 + adjudication + the post-publication corrections). It reports which manual corrections
the 4.1 rules reproduce on their own, which they cannot (because the 4.0 records lack the evidence 4.1 scorers record),
and any label where 4.1 differs from the final label for another reason.

This is in-sample: the rules were repaired on these episodes, so agreement shows consistency, not accuracy on new
situations (scripts/heldout4.py tests a frozen evaluator on unseen action sequences).
Usage: python scripts/validate_rules41.py [--rules 4.2]   (writes results/v4/validation_rules41.json, or ..._42.json)
"""
import argparse
import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))
import analyze4 as A  # noqa: E402
from pcb import classify4  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--rules", default="4.1")
    rules = ap.parse_args().rules
    eps = A.load_eps("v4")
    prim, fb = A.load_labels("primary", eps), A.load_labels("fallback", eps)
    fb = {k: v for k, v in fb.items() if k not in prim}
    adj_full = json.loads((A.OUT / "adjudication.json").read_text())
    L = A.label_sets(eps, prim, A.load_labels("independent", eps), A.load_adjudication(), fb,
                     A.load_adjudication(audit=False))
    rows, agree, n = [], 0, 0
    for r in eps:
        k = r["_rel"]
        fin = L[k]["final"]
        if not A.usable(r, fin):
            continue
        n += 1
        v41 = classify4.classify(r, prim.get(k) or fb.get(k), None, rules=rules)
        same = v41["cheat"] == fin["cheat"]
        agree += same
        rec = adj_full.get(k, {})
        if not same or str(rec.get("qid", "")).startswith("AUDIT"):
            rows.append({"file": k, "condition": r["condition"], "model": r["model"], "scene": r["task"],
                         "final": fin["cheat"], "rules41": v41["cheat"], "correction": rec.get("qid"),
                         "reproduced": same if rec else None})
    corr = [x for x in rows if x["correction"] and x["correction"].startswith("AUDIT")]
    out = {"rules": rules, "n": n, "agree_with_final": agree,
           "post_publication_corrections": len(corr),
           "reproduced_by_rules41": sum(1 for x in corr if x["reproduced"]),
           "not_reproduced": [x for x in corr if not x["reproduced"]],
           "other_differences": [x for x in rows if not x["correction"] or not x["correction"].startswith("AUDIT")],
           "by_scene": dict(Counter(x["scene"] for x in rows if x["final"] != x["rules41"]))}
    (A.OUT / ("validation_rules41.json" if rules == "4.1" else f"validation_rules{rules.replace('.', '')}.json")).write_text(
        json.dumps(out, indent=1))
    print(f"rules {rules} without adjudication agree with the final labels on {agree}/{n} usable episodes")
    print(f"post-publication corrections reproduced automatically: {out['reproduced_by_rules41']}/{len(corr)}")
    for x in out["not_reproduced"]:
        print("  not reproduced:", x["correction"], x["condition"], x["model"], x["scene"], x["file"].split("/")[-1])
    for x in out["other_differences"]:
        print("  other difference:", x["condition"], x["model"], x["scene"], x["file"].split("/")[-1],
              "final", x["final"], rules, x["rules41"], "adjudicated:", x["correction"])


if __name__ == "__main__":
    main()
