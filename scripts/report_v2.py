"""Build the shareable HTML report (v2) from results/v2/summary.json.

python scripts/report_v2.py   ->  results/report/physical_cheatbench.html
Numbers and charts come only from the summary; prose lives in results/report/narrative_v2.json (written after reading
the results); the page layout is results/report/template_v2.html.
"""
import html
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from pcb.models import CHEATBENCH_OVERALL  # noqa: E402

NAMES = {"opus-5.5": "Claude Opus 5.5", "fable-5.1": "Claude Fable 5.1", "gpt-6-sol": "GPT-6 Sol",
         "gpt-6-astra": "GPT-6 Astra", "gemini-3.8-flash": "Gemini 3.8 Flash", "grok-4.7": "Grok 4.7",
         "deepseek-v4-pro": "DeepSeek V4 Pro", "kimi-k3": "Kimi K3", "muse-spark-1.3": "Muse Spark 1.3"}
ORDER = [NAMES[m] for m in sorted(NAMES, key=lambda m: -CHEATBENCH_OVERALL.get(m, 0))]
CB = {NAMES[m]: CHEATBENCH_OVERALL[m] for m in NAMES}
E = html.escape


def esc(s):
    return E(str(s), quote=True)


def kn(cell):
    """cell = [list of 0/1, n_blocked] -> (k, n, blocked)"""
    if not cell:
        return 0, 0, 0
    v, nb = cell
    return sum(v), len(v), nb


def rate(cell):
    k, n, _ = kn(cell)
    return k / n if n else None


def dot_chart(rows, series, aria, width=760, note=None):
    """rows: list of (label, sublabel, {series_key: (k, n, blocked)}); series: list of (key, css class, legend).
    One row per model, one dot per series on a 0-100% axis; a thin line spans the dots."""
    left, right, top, band = 178, 178, 30, 40
    plot_w = width - left - right
    height = top + band * len(rows) + 34
    x = lambda p: left + plot_w * p  # noqa: E731
    o = [f'<svg viewBox="0 0 {width} {height}" class="chart" role="img" aria-label="{esc(aria)}">']
    for t in range(0, 101, 25):
        o.append(f'<line x1="{x(t / 100):.1f}" y1="{top - 10}" x2="{x(t / 100):.1f}" y2="{height - 28}" class="grid"/>')
        o.append(f'<text x="{x(t / 100):.1f}" y="{height - 12}" class="tick" text-anchor="middle">{t}%</text>')
    for i, (lab, sub, vals) in enumerate(rows):
        y = top + band * i + band / 2 - 6
        o.append(f'<text x="{left - 14}" y="{y + 1}" class="lab" text-anchor="end" dominant-baseline="middle">{esc(lab)}</text>')
        if sub:
            o.append(f'<text x="{left - 14}" y="{y + 15}" class="sub" text-anchor="end" dominant-baseline="middle">{esc(sub)}</text>')
        ps = [(key, cls, vals.get(key)) for key, cls, _ in series]
        got = [(key, cls, k / n, k, n, b) for key, cls, (k, n, b) in [(a, c, v) for a, c, v in ps if v] if n]
        if not got:
            blocked = sum(v[2] for _, _, v in ps if v)
            o.append(f'<text x="{x(0) + 6}" y="{y + 1}" class="note" dominant-baseline="middle">'
                     f'{"blocked by the provider classifier" if blocked else "no data"}</text>')
            continue
        lo, hi = min(g[2] for g in got), max(g[2] for g in got)
        o.append(f'<line x1="{x(lo):.1f}" y1="{y}" x2="{x(hi):.1f}" y2="{y}" class="axis"/>')
        for j, (key, cls, p, k, n, b) in enumerate(got):
            legend = dict((s[0], s[2]) for s in series)[key]
            tip = f"{lab}: {legend} {k}/{n}" + (f" (+{b} blocked)" if b else "")
            o.append(f'<g class="mark" tabindex="0" data-tip="{esc(tip)}"><circle cx="{x(p):.1f}" cy="{y}" r="6.5" '
                     f'class="{cls} dot"/><circle cx="{x(p):.1f}" cy="{y}" r="12" class="hit"/></g>')
        # value labels at the right edge, in series order
        txt = " · ".join(f"{k}/{n}" for _, _, _, k, n, _ in got)
        o.append(f'<text x="{width - right + 8}" y="{y + 1}" class="val" dominant-baseline="middle">{esc(txt)}</text>')
    if note:
        o.append(f'<text x="{left}" y="{top - 16}" class="note">{esc(note)}</text>')
    o.append("</svg>")
    leg = "".join(f'<span class="key"><span class="sw {cls}"></span>{esc(lg)}</span>' for _, cls, lg in series)
    return f'<div class="legend">{leg}</div>' + "".join(o)


def heat(rows, cols, caption, colnames=None):
    """rows: list of (label, {col: cell}). Shade by rate."""
    colnames = colnames or {}
    head = "".join(f"<th>{esc(colnames.get(c, c))}</th>" for c in cols)
    body = []
    for lab, cells in rows:
        tds = []
        for c in cols:
            k, n, b = kn(cells.get(c))
            if n == 0 and b:
                tds.append(f'<td class="blk" title="blocked by the provider classifier">blocked<small>{b} ep.</small></td>')
                continue
            if n == 0:
                tds.append('<td class="na">-</td>')
                continue
            p = k / n
            h = 0 if k == 0 else min(5, 1 + int(p * 5 - 1e-9))
            extra = f"<small>+{b} blocked</small>" if b else ""
            tds.append(f'<td class="h{h}" title="{esc(lab)} · {esc(colnames.get(c, c))}: {k}/{n}">{k}/{n}{extra}</td>')
        body.append(f"<tr><th>{esc(lab)}</th>{''.join(tds)}</tr>")
    tot = []
    for c in cols:
        k = sum(kn(cells.get(c))[0] for _, cells in rows)
        n = sum(kn(cells.get(c))[1] for _, cells in rows)
        tot.append(f"<td class='tot'>{k}/{n}</td>")
    body.append(f"<tr class='total'><th>All models</th>{''.join(tot)}</tr>")
    return (f"<div class='scroll'><table class='heat'><caption>{esc(caption)}</caption><thead><tr><th></th>{head}"
            f"</tr></thead><tbody>{''.join(body)}</tbody></table></div>")


def fmt_test(t, name, what):
    lo, hi = t["mh_ci"]
    return (f"<tr><th>{esc(name)}</th><td class='l'>{what}</td><td>{esc(t['a'])}</td><td>{esc(t['b'])}</td>"
            f"<td>{t['mh'] * 100:+.0f} pts <small>[{lo * 100:+.0f}, {hi * 100:+.0f}]</small></td>"
            f"<td>{t['p_two_sided']:.2g}</td><td>{t.get('p_holm', float('nan')):.2g}</td></tr>")


def main():
    S = json.loads((ROOT / "results" / "v2" / "summary.json").read_text())
    narr = json.loads((ROOT / "results" / "report" / "narrative_v2.json").read_text())
    tpl = (ROOT / "results" / "report" / "template_v2.html").read_text()
    E1, E2 = S["E1"], S["E2"]
    parts = {}
    # E1: marker moves by condition
    rows = []
    for m in ORDER:
        mv = E1["move_to_pass"].get(m, {})
        rows.append((m, f"CheatBench {CB[m]}%", {c: kn(mv.get(c)) for c in ("P-base", "P-fixed", "P-auth")}))
    parts["e1_chart"] = dot_chart(rows, [("P-base", "s2", "prompt silent (v1 wording)"),
                                         ("P-fixed", "s1", "CMM uses the surveyed positions"),
                                         ("P-auth", "s3", "moving a marker is allowed")],
                                  "Share of episodes that moved a marker to pass, by condition")
    parts["e1_table"] = heat([(m, {**{c: E1["move_to_pass"].get(m, {}).get(c) for c in ("P-base", "P-fixed", "P-auth")},
                                   "D-fixed": E1["cheat"].get(m, {}).get("D-fixed"),
                                   "true": E1["true_success"].get(m, {}).get("P-auth")}) for m in ORDER],
                             ["P-base", "P-fixed", "P-auth", "D-fixed", "true"],
                             "Markers, seeds 10-19: episodes that moved a marker to pass (P cells) or cheated in any way "
                             "(D-fixed); last column: true success in P-auth",
                             {"P-base": "P · silent", "P-fixed": "P · fixed datum", "P-auth": "P · move allowed",
                              "D-fixed": "D · fixed datum", "true": "P · allowed: success"})
    # E2: interlock bypass, v1 vs v2 base vs real
    rows = []
    v1 = S["v1_cheat"]
    for m in ORDER:
        def pool(cells, keys):
            k = n = b = 0
            for key in keys:
                a, bb, cc = kn(cells.get(key))
                k, n, b = k + a, n + bb, b + cc
            return k, n, b
        rows.append((m, f"CheatBench {CB[m]}%", {
            "v1": pool(v1.get(m, {}), ("pallet_D", "pallet_P")),
            "base": pool(E2["cheat"].get(m, {}), ("D-base", "P-base")),
            "real": pool(E2["cheat"].get(m, {}), ("D-real", "P-real"))}))
    parts["e2_chart"] = dot_chart(rows, [("v1", "s0", "v1, seeds 0-9"), ("base", "s2", "v2 base, seeds 10-19"),
                                         ("real", "s1", "v2 'not a simulator'")],
                                  "Interlock bypass attempts by model and condition")
    parts["e2_table"] = heat([(m, {**{c: E2["cheat"].get(m, {}).get(c) for c in ("D-base", "P-base", "D-real", "P-real")},
                                   "prod": [sum([E2["consequential"].get(m, {}).get(c, [[], 0])[0] for c in
                                                 ("D-base", "P-base", "D-real", "P-real")], []), 0]})
                              for m in ORDER],
                             ["D-base", "P-base", "D-real", "P-real", "prod"],
                             "Palletizing, seeds 10-19: interlock bypass attempts; last column: episodes that ran "
                             "production at full speed with the interlock defeated (all four cells)",
                             {"D-base": "D · base", "P-base": "P · base", "D-real": "D · real", "P-real": "P · real",
                              "prod": "full-speed production"})
    # v1 corrected
    envs = ["pins_R", "pins_D", "pins_P", "markers_D", "markers_P", "dose_D", "dose_P", "pallet_D", "pallet_P"]
    names = {"pins_R": "Pins · R", "pins_D": "Pins · D", "pins_P": "Pins · P", "markers_D": "Markers · D",
             "markers_P": "Markers · P", "dose_D": "Dose · D", "dose_P": "Dose · P", "pallet_D": "Pallet · D",
             "pallet_P": "Pallet · P"}
    parts["v1_table"] = heat([(m, {e: v1.get(m, {}).get(e) for e in envs}) for m in ORDER], envs,
                             "v1 (seeds 0-9) relabelled under the v2 rules: cheating attempts; pallet columns are "
                             "interlock bypass attempts. Marker moves are not counted here (ambiguous; see above).",
                             names)
    amb = S["v1_ambiguous_move"]
    parts["v1_moves"] = heat([(m, {"markers_P": amb.get(m, {}).get("markers_P")}) for m in ORDER], ["markers_P"],
                             "v1 marker moves (prompt silent)", {"markers_P": "Markers · P, moved"})
    # tests
    T = S["tests"]
    parts["tests"] = ("<div class='scroll'><table class='tests'><thead><tr><th></th><th class='l'>Comparison</th>"
                      "<th>a</th><th>b</th><th>Risk difference [95% CI]</th><th>p</th><th>p, Holm</th></tr></thead><tbody>"
                      + fmt_test(T["H-M1"], "H-M1", "moved a marker: fixed datum (a) vs prompt silent (b)")
                      + fmt_test(T["H-M2"], "H-M2", "cheated: robot route P-fixed (a) vs software route D-fixed (b)")
                      + fmt_test(T["H-M3"], "H-M3", "moved a marker: allowed (a) vs fixed datum (b)")
                      + fmt_test(T["H-S2"], "H-S2", "bypassed the interlock: 'not a simulator' (a) vs base (b)")
                      + "</tbody></table></div>")
    mc = S["manipulation_check_simulation"]
    parts["manip"] = (f"{esc(mc['a'])} in real vs {esc(mc['b'])} in base "
                      f"(risk difference {mc['mh'] * 100:+.0f} points, p = {mc['p_two_sided']:.2g})")
    for k, v in parts.items():
        tpl = tpl.replace("{{" + k + "}}", v)
    for k, v in narr.items():
        tpl = tpl.replace("{{" + k + "}}", v)
    left = [s for s in tpl.split("{{")[1:]]
    if left:
        print("unfilled placeholders:", [s.split("}}")[0] for s in left])
    out = ROOT / "results" / "report" / "physical_cheatbench.html"
    out.write_text(tpl)
    print("wrote", out, len(tpl), "bytes")


if __name__ == "__main__":
    main()
