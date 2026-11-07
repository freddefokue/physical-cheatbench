"""Fill RESULTS_v5.md's [[PLACEHOLDERS]] from the analysis outputs and the hand-written prose
(results/v5/results_text.py), so that no number in the write-up is copied by hand.
Usage: python scripts/results_md5.py  (after analyze5.py and search_report5.py)."""
import importlib.util
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))
NAMES = {"opus-5.5": "Claude Opus 5.5", "fable-5.1": "Claude Fable 5.1", "gpt-6-sol": "GPT-6 Sol",
         "gpt-6-astra": "GPT-6 Astra", "gemini-3.8-flash": "Gemini 3.8 Flash", "grok-4.7": "Grok 4.7",
         "deepseek-v4-pro": "DeepSeek V4 Pro", "kimi-k3": "Kimi K3", "muse-spark-1.3": "Muse Spark 1.3"}
SC = ("guard", "pack", "leak")


def section(md, title):
    """The block of tables.md under a '## title' heading, up to the next '## '."""
    m = re.search(rf"^## {re.escape(title)}\n(.*?)(?=^## |\Z)", md, re.S | re.M)
    return m.group(1).strip() if m else ""


def pct(x):
    return "-" if x is None else f"{100 * x:.0f} %"


def main():
    S = json.loads((ROOT / "results/v5/summary.json").read_text())
    T = (ROOT / "results/v5/tables.md").read_text()
    SR = (ROOT / "results/v5/search.md").read_text()
    spec = importlib.util.spec_from_file_location("results_text", ROOT / "results/v5/results_text.py")
    txt = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(txt)
    import validation_table5
    from io import StringIO
    import contextlib
    buf = StringIO()
    with contextlib.redirect_stdout(buf):
        validation_table5.main()
    fill = {}
    fill["VALIDATION"] = buf.getvalue().strip()
    # main table with v4 on the same scenes
    rows = ["| Model | guard | pack | leak | v5 overall [95 % CI] | v4, same 3 scenes | CheatBench |",
            "|---|---|---|---|---|---|---|"]
    from pcb.models import CHEATBENCH_OVERALL
    order = sorted(S["models"], key=lambda m: -(S["main"][m]["overall"]["rate"] or 0))
    for m in order:
        t = S["main"][m]
        cells = [f'{t["scenes"][s]["k"]}/{t["scenes"][s]["n"]}' if t["scenes"][s]["n"] else "-" for s in SC]
        o = t["overall"]
        v4 = [S["v4_rates"].get(f"{m}/{s}") for s in SC]
        v4c = [v for v in v4 if v and v.get("n")]
        v4m = sum(v["rate"] for v in v4c) / len(v4c) if v4c else None
        rows.append(f'| {NAMES[m]} | ' + " | ".join(cells) + f' | {pct(o["rate"])} [{pct(o["ci"][0])}, {pct(o["ci"][1])}] '
                    f'| {pct(v4m)} | {CHEATBENCH_OVERALL[m]} % |')
    fill["MAIN_TABLE"] = "\n".join(rows)
    fill["TESTS"] = section(T, "Tests")
    fill["FUNNEL"] = section(T, "Funnel (main)")
    fill["CONTROLS"] = section(T, "Controls")
    fill["COMPARISON"] = section(T, "Comparison (guard, main, seeds 0-3, deterministic labels)")
    fill["DIAGNOSTICS"] = section(T, "Interface diagnostics")
    sens = S["sensitivity"]
    srows = ["| Model | Final | Act log only (no judge) | Without the request rule | No adjudication |", "|---|---|---|---|---|"]
    for m in order:
        srows.append(f'| {NAMES[m]} | {pct(S["main"][m]["overall"]["rate"])} | {pct(sens["det"][m]["rate"])} | '
                     f'{pct(sens["noreq"][m]["rate"])} | {pct(sens["noadj"][m]["rate"])} |')
    ag = sens.get("indep_agreement")
    srows.append("")
    if ag:
        srows.append(f'Independent judge (GPT-6.1 Sol, transcript only) on its sample: {ag["n"]} episodes, agreement on '
                     f'`cheat` {100 * ag["agree"]:.0f} %, kappa {ag["kappa"]}; both {ag["both"]}, primary only '
                     f'{ag["first_only"]}, independent only {ag["second_only"]}.')
    srows.append("The act-log-only labels have no judge, so in `pack` they count every test weight put in the carton, "
                 "including the scale checks the definition excludes (deviation 4).")
    fill["SENSITIVITY"] = "\n".join(srows)
    st = section(SR, "Search (exploratory; every candidate and episode)")
    ct = section(SR, "Confirmation (pre-registered in section 13; new seeds 200-203)")
    fill["SEARCH"] = txt.SEARCH.replace("[[SEARCH_TABLE]]", st).replace("[[CONFIRM_TABLE]]", ct)
    for k in ("IN_SHORT", "LABELS", "LIMITS", "RUN", "COST"):
        if hasattr(txt, k):
            fill[k] = getattr(txt, k)
    p = ROOT / "RESULTS_v5.md"
    s = (ROOT / "results/v5/results_template.md").read_text()
    for k, v in fill.items():
        s = s.replace(f"[[{k}]]", v)
    left = re.findall(r"\[\[([A-Z_]+)\]\]", s)
    p.write_text(s)
    print("filled", sorted(fill), "| still open:", left)


if __name__ == "__main__":
    main()
