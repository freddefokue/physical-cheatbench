"""Judge v5 descriptions for episodes (pcb5/judge5.py, PLAN_v5.md section 5). Resumable; results in
results/v5/labels/<which>.jsonl, one line per episode: {"file": <record path>, "label": {...}}.

  python scripts/label5.py --which primary runs/v5/main runs/v5/dont_cheat ...
  python scripts/label5.py --which independent --sample results/v5/labels/independent_sample.txt
  python scripts/label5.py --make-sample runs/v5/main ...   (the random 25 % sample, stratified by scene, seed 5)
Episodes whose primary labelling the provider refuses are labelled by the fallback judge (the independent judge's
model with the primary prompt): --which fallback. Requires PCB_CAP_OPENROUTER.
"""
import argparse
import json
import os
import random
import sys
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
OUT = ROOT / "results" / "v5" / "labels"


def load_env():
    for line in (ROOT / ".env").read_text().splitlines():
        if "=" in line and not line.strip().startswith("#"):
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip())


def labels_by_file(which):
    p = OUT / f"{which}.jsonl"
    out = {}
    if p.exists():
        for line in p.read_text().splitlines():
            try:
                d = json.loads(line)
            except ValueError:
                continue
            out.setdefault(d["file"], []).append(d["label"])
    return out


def episode_files(roots):
    for root in roots:
        for f in sorted((ROOT / root).rglob("*.json")):
            if ".inspect" in str(f) or f.name.endswith(".llm.json"):
                continue
            yield f


def load_episode(f):
    r = json.loads(Path(f).read_text())
    r["_llm_path"] = str(Path(f).with_suffix("")) + ".llm.jsonl"
    r["_rel"] = str(Path(f).relative_to(ROOT))
    return r


def labelable(r):
    from pcb5.classify5 import blocked
    # the comparison variants are labelled from their act logs (PLAN_v5.md section 7), not by the judges
    return "outcome" in r and r.get("task") in ("guard", "pack", "leak") and not blocked(r) and \
        r.get("end_reason") in ("final", "limit", "provider_refusal")


def make_sample(files, frac=0.25, seed=5):
    """A random sample stratified by scene (and condition), as v4's independent sample."""
    rng = random.Random(seed)
    by = {}
    for f in files:
        r = load_episode(f)
        if labelable(r):
            by.setdefault((r["task"], r["condition"]), []).append(r["_rel"])
    out = []
    for k in sorted(by):
        xs = sorted(by[k])
        rng.shuffle(xs)
        out += sorted(xs[: max(1, round(frac * len(xs)))])
    return out


def main():
    load_env()
    from pcb5 import judge5
    ap = argparse.ArgumentParser()
    ap.add_argument("roots", nargs="*")
    ap.add_argument("--which", choices=["primary", "independent", "fallback"])
    ap.add_argument("--sample", help="file with one episode path (relative to the repo) per line")
    ap.add_argument("--make-sample", action="store_true")
    ap.add_argument("--workers", type=int, default=8)
    ap.add_argument("--limit", type=int, default=0)
    a = ap.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    if a.make_sample:
        s = make_sample(list(episode_files(a.roots)))
        (OUT / "independent_sample.txt").write_text("\n".join(s) + "\n")
        print(f"{len(s)} episodes in the sample")
        return
    if not os.environ.get("PCB_CAP_OPENROUTER"):
        sys.exit("set PCB_CAP_OPENROUTER")
    files = ([ROOT / x.strip() for x in (ROOT / a.sample).read_text().splitlines() if x.strip()] if a.sample
             else list(episode_files(a.roots)))
    have = labels_by_file(a.which)
    todo = []
    for f in files:
        r = load_episode(f)
        if any(judge5.label_ok(lab) for lab in have.get(r["_rel"], [])) or not labelable(r):
            continue
        if a.which == "fallback":
            prim = [lab for lab in labels_by_file("primary").get(r["_rel"], []) if lab.get("_version") == judge5.version()]
            if not prim or not all("parse_error" in lab for lab in prim):
                continue                     # only episodes whose primary labelling failed
        todo.append(r)
    if a.limit:
        todo = todo[: a.limit]
    print(f"{len(todo)} episodes to label with the {a.which} judge (version {judge5.version()})", flush=True)
    lock = threading.Lock()
    path = OUT / f"{a.which}.jsonl"

    def one(r):
        lab = judge5.judge(r, a.which)
        with lock, path.open("a") as fh:
            fh.write(json.dumps({"file": r["_rel"], "label": lab}, default=str) + "\n")
        return r["_rel"], ("parse_error" in lab), lab.get("_cost")

    with ThreadPoolExecutor(a.workers) as ex:
        futs = [ex.submit(one, r) for r in todo]
        for fu in as_completed(futs):
            try:
                print(fu.result(), flush=True)
            except Exception as e:  # noqa: BLE001
                print("ERROR", repr(e)[:300], flush=True)


if __name__ == "__main__":
    main()
