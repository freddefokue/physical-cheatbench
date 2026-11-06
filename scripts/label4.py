"""Judge v4 descriptions for episodes (pcb/judge4.py). Resumable; results in results/v4/labels/<which>.jsonl.

Example: python scripts/label4.py --which primary runs/v4
         python scripts/label4.py --which independent runs/v4
Requires PCB_CAP_OPENROUTER (USD, project total).
"""
import argparse
import json
import os
import sys
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
OUT = ROOT / "results" / "v4" / "labels"


def load_env():
    for line in (ROOT / ".env").read_text().splitlines():
        if "=" in line and not line.strip().startswith("#"):
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip())


def done_labels(which, version):
    p = OUT / f"{which}.jsonl"
    out = {}
    if p.exists():
        for line in p.read_text().splitlines():
            try:
                d = json.loads(line)
            except ValueError:
                continue
            if d["label"].get("_version") == version and "parse_error" not in d["label"]:
                out[d["file"]] = d["label"]
    return out


def episode_files(roots):
    for root in roots:
        for f in sorted((ROOT / root).rglob("*.json")):
            if f.parent.name == "images":
                continue
            yield f


def main():
    load_env()
    from pcb import judge4
    from pcb.classify import blocked
    ap = argparse.ArgumentParser()
    ap.add_argument("roots", nargs="*")
    ap.add_argument("--which", choices=list(judge4.JUDGES), required=True)
    ap.add_argument("--sample", help="file with one episode path (relative to the repo) per line")
    ap.add_argument("--workers", type=int, default=8)
    ap.add_argument("--limit", type=int, default=0)
    a = ap.parse_args()
    if not os.environ.get("PCB_CAP_OPENROUTER"):
        sys.exit("set PCB_CAP_OPENROUTER")
    files = ([ROOT / l.strip() for l in (ROOT / a.sample).read_text().splitlines() if l.strip()] if a.sample
             else list(episode_files(a.roots)))
    ver = judge4.version()
    have = done_labels(a.which, ver)
    todo = []
    for f in files:
        rel = str(f.relative_to(ROOT))
        if rel in have:
            continue
        try:
            r = json.loads(f.read_text())
        except ValueError:
            continue
        if "turns" not in r or blocked(r) or r.get("end_reason") in ("exception", "budget", None):
            continue
        todo.append((rel, r))
    if a.limit:
        todo = todo[: a.limit]
    print(f"{a.which}: {len(todo)} to label (version {ver}, {len(have)} done)", flush=True)
    OUT.mkdir(parents=True, exist_ok=True)
    lock = threading.Lock()
    from openai import OpenAI
    client = OpenAI(base_url="https://openrouter.ai/api/v1", api_key=os.environ["OPENROUTER_API_KEY_2"],
                    max_retries=2, timeout=900)
    n_err = 0
    with ThreadPoolExecutor(a.workers) as ex:
        futs = {ex.submit(judge4.judge, r, a.which, client): rel for rel, r in todo}
        for i, fu in enumerate(as_completed(futs)):
            rel = futs[fu]
            try:
                lab = fu.result()
            except Exception as e:  # noqa: BLE001
                print(f"  {rel}: {e}", flush=True)
                n_err += 1
                continue
            with lock, open(OUT / f"{a.which}.jsonl", "a") as fh:
                fh.write(json.dumps({"file": rel, "label": lab}) + "\n")
            if "parse_error" in lab:
                n_err += 1
            if i % 25 == 0:
                print(f"  [{i + 1}/{len(todo)}] {rel} ${lab.get('_cost', 0):.3f}", flush=True)
    print(f"done; {n_err} errors", flush=True)


if __name__ == "__main__":
    main()
