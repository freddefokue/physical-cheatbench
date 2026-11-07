"""The validation table of PLAN_v5.md section 11, from results/v5/validation.json (scripts/validate5.py)."""
import json
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def main():
    res = json.loads((ROOT / "results" / "v5" / "validation.json").read_text())
    rows = defaultdict(lambda: {"n": 0, "check": 0, "true": 0, "false_pass": 0, "logged": 0, "time": []})
    for key, r in res.items():
        scene, cond, mode, _seed = key.split("/")
        row = rows[(scene, cond, mode)]
        row["n"] += 1
        row["check"] += bool(r["check_passed"])
        row["true"] += bool(r["true_success"])
        row["false_pass"] += bool(r["check_passed"] and not r["true_success"])
        acts = set(r.get("acts") or [])
        want = {"shortcut": {"actuator_in_sensor", "ballast_in_check", "substitution"},
                "shortcut_D": {"file_edit"}}.get(mode, set())
        row["logged"] += bool(acts & want)
        row["time"].append(r.get("robot_time"))
    lines = ["| Scene | Condition | Scripted policy | Check passed | True success | False pass | Act logged | "
             "Robot time (s, mean) |", "|---|---|---|---|---|---|---|---|"]
    order = {"honest": 0, "shortcut": 1, "shortcut_D": 2}
    for (scene, cond, mode), row in sorted(rows.items(), key=lambda kv: (["guard", "pack", "leak"].index(kv[0][0]),
                                                                        kv[0][1] != "honest_ok", order[kv[0][2]])):
        n = row["n"]
        logged = f"{row['logged']}/{n}" if mode != "honest" else "-"
        t = [x for x in row["time"] if x is not None]
        lines.append(f"| {scene} | {cond} | {mode} | {row['check']}/{n} | {row['true']}/{n} | {row['false_pass']}/{n} | "
                     f"{logged} | {sum(t) / len(t):.0f} |")
    print("\n".join(lines))


if __name__ == "__main__":
    main()
