"""Print an episode transcript compactly. Usage: python scripts/show.py runs/<run>/<cond>/<model>/<env>/<seed>.json [--full]"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from pcb.judge import transcript_text  # noqa: E402

for path in [a for a in sys.argv[1:] if not a.startswith("--")]:
    r = json.loads(Path(path).read_text())
    full = "--full" in sys.argv
    print(f"##### {r['id']}  end={r.get('end_reason')} turns={r.get('n_turns')} calls={r.get('n_tool_calls')} "
          f"cost=${r.get('cost')} wall={r.get('wall_s')}s exposure={r.get('exposure')} canary={r.get('canary')}")
    if r.get("error"):
        print("ERROR:", r["error"])
    print(transcript_text(r, out_chars=100000 if full else 700, reason_chars=100000 if full else 1200))
    print("\nFINAL:", r.get("final_text"))
    o = r.get("outcome", {})
    print("\nOUTCOME:", json.dumps({k: v for k, v in o.items() if k not in ("mark_moves", "weight_events", "last_check")},
                                   default=str)[:1500])
    if r.get("label"):
        print("\nLABEL:", json.dumps(r["label"], indent=1)[:3000])
