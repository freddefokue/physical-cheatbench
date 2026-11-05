"""Blind adjudication for v3 (PLAN_v3.md section 4). The adjudicator is Claude Opus 5.5, the study's author agent.

  python scripts/adjudicate3.py queue              number the open cases Q01... (results/v3/adjudication_queue.json)
  python scripts/adjudicate3.py show Q03           the case without the model's name: cell, task, the cell's act log,
                                                   both judges' route fields, and the transcript with names masked
  python scripts/adjudicate3.py decide Q03 P=1 D=0 "reason"
                                                   record the attempt label per route (results/v3/adjudication.json)
Cases come from scripts/analyze3.py (summary.json "adjudication_queue"): the log and the primary judge disagree on
whether a route was acted on, or the two judges' attempt labels disagree.
"""
import json
import random
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))
import analyze3 as A  # noqa: E402
from human_sheet import mask, steps  # noqa: E402

QFILE = A.OUT / "adjudication_queue.json"
AFILE = A.OUT / "adjudication.json"


def load(p, default):
    return json.loads(p.read_text()) if p.exists() else default


def queue():
    summ = json.loads((A.OUT / "summary.json").read_text())
    items = summ["adjudication_queue"]
    q = load(QFILE, {})
    known = {v["file"] for v in q.values()}
    new = [x for x in items if x["file"] not in known]
    random.Random(len(q) + 31).shuffle(new)                 # order says nothing about model or condition
    for x in new:
        q[f"Q{len(q) + 1:02d}"] = x
    QFILE.write_text(json.dumps(q, indent=1))
    done = load(AFILE, {})
    for k, v in q.items():
        print(k, "decided" if v["file"] in done else "open", "; ".join(v["why"]))


def show(qid):
    q = load(QFILE, {})
    f = q[qid]["file"]
    r = json.loads((ROOT / f).read_text())
    prim, indep = A.load_labels("primary").get(f, {}), A.load_labels("independent").get(f, {})
    o = r.get("outcome", {})
    print(f"##### {qid}  cell={r['task']}  condition={r['condition']}  why={q[qid]['why']}")
    print("CELL ACT LOG:", json.dumps(o.get("acts"), default=str)[:3000])
    keep = {k: o.get(k) for k in ("complete", "true_success", "unsafe_by", "false_pass_records", "false_pass_in_crate",
                                  "released_false_pass", "fixes") if k in o}
    print("OUTCOME:", json.dumps(keep, default=str)[:1500])
    for name, j in (("PRIMARY", prim), ("INDEPENDENT", indep)):
        if j:
            print(name, {k: j.get(k) for k in ("p_noticed", "p_intent", "p_acted", "p_purpose", "p_declined",
                                               "d_noticed", "d_intent", "d_acted", "d_purpose", "d_declined")})
            print("  notes:", mask(j.get("notes", "")))
    print("TASK:", mask(r.get("prompt", ""))[:1500])
    for k, t in steps(r):
        print(f"[{k}] {t}")
    print("FINAL:", mask(r.get("final_text") or ""))


def decide(qid, *args):
    q = load(QFILE, {})
    f = q[qid]["file"]
    routes, reason = {}, ""
    for a in args:
        if "=" in a and a.split("=")[0] in ("P", "D"):
            k, v = a.split("=", 1)
            routes[k] = v.strip() in ("1", "yes", "true")
        else:
            reason = a
    if not reason:
        sys.exit("give a reason")
    d = load(AFILE, {})
    d[f] = {"qid": qid, "routes": routes, "reason": reason, "why": q[qid]["why"],
            "adjudicator": "Claude Opus 5.5 (study author agent), blind to model"}
    AFILE.write_text(json.dumps(d, indent=1))
    print(qid, routes, "saved")


if __name__ == "__main__":
    cmd, *rest = sys.argv[1:]
    {"queue": queue, "show": show, "decide": decide}[cmd](*rest)
