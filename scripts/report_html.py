"""Build the shareable HTML report from analysis summaries.

Usage: python scripts/report_html.py results/main_base/summary_judge.json [results/main_dont_cheat/summary_judge.json]
Writes results/report/physical_cheatbench.html. Narrative text lives in results/report/narrative.json (written by
hand after reading the results); numbers come only from the summaries.
"""
import html
import json
import math
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from pcb.models import CHEATBENCH_OVERALL  # noqa: E402

NAMES = {"opus-5.5": "Claude Opus 5.5", "fable-5.1": "Claude Fable 5.1", "gpt-6-sol": "GPT-6 Sol",
         "gpt-6-astra": "GPT-6 Astra", "gemini-3.8-flash": "Gemini 3.8 Flash", "grok-4.7": "Grok 4.7",
         "deepseek-v4-pro": "DeepSeek V4 Pro", "kimi-k3": "Kimi K3", "muse-spark-1.3": "Muse Spark 1.3"}
MAIN = ["pins_R", "pins_D", "pins_P", "markers_D", "markers_P", "dose_D", "dose_P"]
EXT = ["pallet_D", "pallet_P"]
ENV_LABEL = {"pins_R": "Pins · R", "pins_D": "Pins · D", "pins_P": "Pins · P", "markers_D": "Markers · D",
             "markers_P": "Markers · P", "dose_D": "Dose · D", "dose_P": "Dose · P", "pallet_D": "Pallet · D",
             "pallet_P": "Pallet · P"}
E = html.escape


def esc(s):
    return E(str(s), quote=True)


def cell(summary, m, e):
    return summary["cells"].get(f"{m}|{e}")


def pooled(summary, m, envs):
    cs = [cell(summary, m, e) for e in envs]
    cs = [c for c in cs if c and c.get("n")]
    k, n = sum(c["cheat"] for c in cs), sum(c["n"] for c in cs)
    b = sum((cell(summary, m, e) or {}).get("blocked", 0) for e in envs)
    return k, n, b


# ---------------------------------------------------------------------------------------------------------------
def route_chart(summary, order):
    """Horizontal grouped bars: per model, R / D / P rates (pooled episodes)."""
    groups = [("R", ["pins_R"], "Read the reference"), ("D", ["pins_D", "markers_D", "dose_D"], "Edit grader input"),
              ("P", ["pins_P", "markers_P", "dose_P"], "Fool the sensor with the robot")]
    left, right, top, band, bh = 168, 60, 36, 58, 13
    width = 760
    plot_w = width - left - right
    height = top + band * len(order) + 34
    o = [f'<svg viewBox="0 0 {width} {height}" class="chart" role="img" aria-label="Cheating rate by route and model">']
    for t in range(0, 101, 25):
        x = left + plot_w * t / 100
        o.append(f'<line x1="{x:.1f}" y1="{top - 8}" x2="{x:.1f}" y2="{height - 26}" class="grid"/>')
        o.append(f'<text x="{x:.1f}" y="{height - 10}" class="tick" text-anchor="middle">{t}%</text>')
    for i, m in enumerate(order):
        y0 = top + band * i
        cb = CHEATBENCH_OVERALL.get(m)
        o.append(f'<text x="{left - 12}" y="{y0 + 22}" class="lab" text-anchor="end">{esc(NAMES.get(m, m))}</text>')
        o.append(f'<text x="{left - 12}" y="{y0 + 36}" class="sub" text-anchor="end">CheatBench {cb}%</text>')
        for gi, (key, envs, name) in enumerate(groups):
            k, n, b = pooled(summary, m, envs)
            y = y0 + 4 + gi * (bh + 2)
            if n == 0:
                o.append(f'<text x="{left + 4}" y="{y + bh - 3}" class="note">blocked by provider classifier</text>')
                continue
            r = k / n
            w = plot_w * r
            tip = f"{NAMES.get(m, m)} · {name}: {k} of {n} episodes ({100 * r:.0f}%)" + (f"; {b} blocked" if b else "")
            if w > 0.5:
                rad = min(4, w / 2)
                o.append(f'<path d="M{left},{y} h{w - rad:.1f} a{rad},{rad} 0 0 1 {rad},{rad} v{bh - 2 * rad} '
                         f'a{rad},{rad} 0 0 1 -{rad},{rad} h-{w - rad:.1f} z" class="s{gi + 1} mark" '
                         f'data-tip="{esc(tip)}" tabindex="0"/>')
            else:
                o.append(f'<rect x="{left}" y="{y}" width="2" height="{bh}" class="s{gi + 1} mark zero" '
                         f'data-tip="{esc(tip)}" tabindex="0"/>')
            o.append(f'<text x="{left + w + 6:.1f}" y="{y + bh - 3}" class="val">{k}/{n}</text>')
    o.append(f'<line x1="{left}" y1="{top - 8}" x2="{left}" y2="{height - 26}" class="axis"/>')
    o.append("</svg>")
    legend = "".join(f'<span class="key"><i class="sw s{i + 1}"></i>{esc(g[2])} ({g[0]})</span>'
                     for i, g in enumerate(groups))
    return f'<div class="legend">{legend}</div><div class="scroll">{"".join(o)}</div>'


def scatter_chart(summary, models):
    """CheatBench overall (x) vs this benchmark's overall rate (mean over the 7 main environments) (y)."""
    width, height, l, r, t, b = 640, 330, 52, 24, 20, 46
    pw, ph = width - l - r, height - t - b
    ymax = 40
    o = [f'<svg viewBox="0 0 {width} {height}" class="chart" role="img" '
         f'aria-label="Overall cheating rate here against CheatBench overall rate">']
    for v in range(0, 101, 25):
        x = l + pw * v / 100
        o.append(f'<line x1="{x:.1f}" y1="{t}" x2="{x:.1f}" y2="{t + ph}" class="grid"/>')
        o.append(f'<text x="{x:.1f}" y="{height - 26}" class="tick" text-anchor="middle">{v}%</text>')
    for v in range(0, ymax + 1, 10):
        y = t + ph * (1 - v / ymax)
        o.append(f'<line x1="{l}" y1="{y:.1f}" x2="{l + pw}" y2="{y:.1f}" class="grid"/>')
        o.append(f'<text x="{l - 8}" y="{y + 3.5:.1f}" class="tick" text-anchor="end">{v}%</text>')
    o.append(f'<text x="{l + pw / 2}" y="{height - 6}" class="tick" text-anchor="middle">CheatBench overall rate (digital tasks)</text>')
    for m in models:
        mm = summary["models"].get(m)
        if not mm or m not in CHEATBENCH_OVERALL:
            continue
        xv, yv = CHEATBENCH_OVERALL[m], 100 * mm["overall"]
        x, y = l + pw * xv / 100, t + ph * (1 - min(yv, ymax) / ymax)
        tip = f"{NAMES.get(m, m)}: CheatBench {xv}% · here {yv:.0f}% (mean of {mm['n_envs']} environments)"
        o.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="5" class="s1 dot mark" data-tip="{esc(tip)}" tabindex="0"/>')
        o.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="13" class="hit" data-tip="{esc(tip)}"/>')
        right = xv < 60
        o.append(f'<text x="{x + (9 if right else -9):.1f}" y="{y + 4:.1f}" class="sub" '
                 f'text-anchor="{"start" if right else "end"}">{esc(NAMES.get(m, m))}</text>')
    o.append(f'<line x1="{l}" y1="{t + ph}" x2="{l + pw}" y2="{t + ph}" class="axis"/>')
    o.append("</svg>")
    return "".join(o)


def heat_table(summary, order, envs, caption):
    rows = []
    head = "".join(f"<th scope='col'>{esc(ENV_LABEL[e])}</th>" for e in envs)
    for m in order:
        tds = []
        for e in envs:
            c = cell(summary, m, e)
            if not c:
                tds.append("<td class='na'>–</td>")
                continue
            n, k, b = c.get("n", 0), c.get("cheat", 0), c.get("blocked", 0)
            if n == 0:
                tds.append(f"<td class='blk' title='all {b} episodes blocked by the provider classifier'>blocked</td>")
                continue
            r = k / n
            lvl = 0 if k == 0 else 1 + min(4, int(r * 5))
            extra = f"<small>+{b} blocked</small>" if b else ""
            tds.append(f"<td class='h{lvl}' title='{k} of {n} episodes'>{k}/{n}{extra}</td>")
        rows.append(f"<tr><th scope='row'>{esc(NAMES.get(m, m))}</th>{''.join(tds)}</tr>")
    return (f"<div class='scroll'><table class='heat'><caption>{esc(caption)}</caption><thead><tr><th></th>{head}"
            f"</tr></thead><tbody>{''.join(rows)}</tbody></table></div>")


def main():
    base = json.loads(Path(sys.argv[1]).read_text())
    abl = json.loads(Path(sys.argv[2]).read_text()) if len(sys.argv) > 2 and Path(sys.argv[2]).exists() else None
    narr_p = ROOT / "results" / "report" / "narrative.json"
    narr = json.loads(narr_p.read_text()) if narr_p.exists() else {}
    order = sorted([m for m in base["models"]], key=lambda m: -CHEATBENCH_OVERALL.get(m, 0))
    parts = {
        "route_chart": route_chart(base, order),
        "scatter": scatter_chart(base, order),
        "heat_main": heat_table(base, order, MAIN, "Cheating attempts per model and environment (episodes)"),
        "heat_ext": heat_table(base, order, EXT, "Safety bypass attempts in the palletizing test (episodes)"),
    }
    if abl:
        parts["heat_abl"] = heat_table(abl, order, ["pins_R", "markers_P"],
                                       "With “Don't cheat!” appended to the task (episodes)")
    tpl = (ROOT / "results" / "report" / "template.html").read_text()
    for k, v in parts.items():
        tpl = tpl.replace("{{" + k + "}}", v)
    for k, v in narr.items():
        tpl = tpl.replace("{{" + k + "}}", v)
    out = ROOT / "results" / "report" / "physical_cheatbench.html"
    out.write_text(tpl)
    print("wrote", out, len(tpl), "bytes")


if __name__ == "__main__":
    main()
