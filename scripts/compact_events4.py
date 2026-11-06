"""Moves the cell's raw request log ("events") of very large v4 run records into a compressed file beside the record,
so that every committed file stays under GitHub's size limits. Lossless: the record keeps the file name, the number
of events and the SHA-256 of the events' JSON; `load_events()` restores them. No analysis reads "events" (the act log
the analysis uses is in "outcome").

Usage: python scripts/compact_events4.py [--min-mb 40] [--dry-run]
"""
import argparse
import gzip
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def load_events(rec_path):
    """The full event list of a record, whether stored inline or in its side file."""
    rec_path = Path(rec_path)
    r = json.loads(rec_path.read_text())
    ev = r.get("events")
    if isinstance(ev, dict) and "events_file" in ev:
        with gzip.open(rec_path.parent / ev["events_file"], "rt") as f:
            return [json.loads(line) for line in f]
    return ev


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--min-mb", type=float, default=40)
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()
    for f in sorted((ROOT / "runs" / "v4").rglob("*.json")):
        if f.stat().st_size < a.min_mb * 1e6:
            continue
        r = json.loads(f.read_text())
        ev = r.get("events")
        if not isinstance(ev, list):
            continue
        digest = hashlib.sha256(json.dumps(ev).encode()).hexdigest()
        side = f.with_name(f"{f.stem}.events.jsonl.gz")
        print(f"{f.relative_to(ROOT)}: {f.stat().st_size / 1e6:.0f} MB, {len(ev)} events -> {side.name}")
        if a.dry_run:
            continue
        with gzip.open(side, "wt", compresslevel=9) as g:
            for e in ev:
                g.write(json.dumps(e) + "\n")
        r["events"] = {"events_file": side.name, "n_events": len(ev), "sha256_of_events_json": digest}
        tmp = f.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(r))
        tmp.replace(f)
        back = load_events(f)
        assert hashlib.sha256(json.dumps(back).encode()).hexdigest() == digest, "round trip failed"
        print(f"  now {f.stat().st_size / 1e6:.1f} MB + {side.stat().st_size / 1e6:.1f} MB (round trip verified)")


if __name__ == "__main__":
    main()
