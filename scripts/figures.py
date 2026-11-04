"""Figures for RESULTS.md from an analysis summary (scripts/analyze.py output).

Usage: python scripts/figures.py results/<name>/summary_judge.json
Palette: dataviz reference instance (validated: slots 1-3 pass all-pairs; aqua needs labels -> values are printed).
"""
import json
import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from pcb.models import CHEATBENCH_OVERALL  # noqa: E402

SURFACE, INK, INK2, MUTED, GRID, AXIS = "#fcfcfb", "#0b0b0b", "#52514e", "#898781", "#e1e0d9", "#c3c2b7"
SERIES = ["#2a78d6", "#eb6834", "#1baf7a"]
SEQ = ["#cde2fb", "#9ec5f4", "#6da7ec", "#3987e5", "#256abf", "#184f95", "#0d366b"]
NAMES = {"opus-5.5": "Claude Opus 5.5", "fable-5.1": "Claude Fable 5.1", "gpt-6-sol": "GPT-6 Sol",
         "gpt-6-astra": "GPT-6 Astra", "gemini-3.8-flash": "Gemini 3.8 Flash", "grok-4.7": "Grok 4.7",
         "deepseek-v4-pro": "DeepSeek V4 Pro", "kimi-k3": "Kimi K3", "muse-spark-1.3": "Muse Spark 1.3"}
ENVS = ["pins_R", "pins_D", "pins_P", "markers_D", "markers_P", "dose_D", "dose_P", "pallet_D", "pallet_P"]


def style(ax):
    ax.set_facecolor(SURFACE)
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)
    for s in ("left", "bottom"):
        ax.spines[s].set_color(AXIS)
        ax.spines[s].set_linewidth(0.8)
    ax.tick_params(colors=INK2, labelsize=9, length=0)
    ax.grid(color=GRID, linewidth=0.6)
    ax.set_axisbelow(True)


def channels(summary, out):
    cells, models = summary["cells"], summary["models"]
    order = sorted(models, key=lambda m: CHEATBENCH_OVERALL.get(m, 0))
    groups = [("R", ["pins_R"], "Read the reference (R)"),
              ("D", ["pins_D", "markers_D", "dose_D"], "Edit grader input (D)"),
              ("P", ["pins_P", "markers_P", "dose_P"], "Fool the sensor with the robot (P)")]
    fig, ax = plt.subplots(figsize=(8.2, 0.62 * len(order) + 1.4), dpi=160)
    fig.patch.set_facecolor(SURFACE)
    style(ax)
    ax.grid(axis="y", visible=False)
    h = 0.24
    for gi, (key, envs, label) in enumerate(groups):
        for mi, m in enumerate(order):
            ks = [cells.get(f"{m}|{e}") for e in envs]
            ks = [c for c in ks if c]
            if not ks:
                continue
            k, n = sum(c["cheat"] for c in ks), sum(c["n"] for c in ks)
            rate = k / n
            y = mi + (1 - gi) * (h + 0.04)
            ax.barh(y, rate * 100, height=h, color=SERIES[gi])
            ax.text(rate * 100 + 1.2, y, f"{k}/{n}", va="center", ha="left", fontsize=7.5, color=INK2)
    ax.set_yticks(range(len(order)))
    ax.set_yticklabels([f"{NAMES.get(m, m)}  ({CHEATBENCH_OVERALL.get(m, '-')}%)" for m in order], color=INK, fontsize=9)
    ax.set_xlim(0, 105)
    ax.set_xlabel("Episodes with a cheating attempt (%)", color=INK2, fontsize=9)
    ax.set_title("Cheating by route in the physical cells\n(models ordered by CheatBench overall rate, in brackets)",
                 color=INK, fontsize=10.5, loc="left")
    from matplotlib.patches import Patch
    leg = ax.legend(handles=[Patch(color=SERIES[i], label=g[2]) for i, g in enumerate(groups)], loc="lower right",
                    frameon=False, fontsize=8.5)
    for t in leg.get_texts():
        t.set_color(INK)
    fig.tight_layout()
    fig.savefig(out, facecolor=SURFACE)
    plt.close(fig)


def scatter(summary, out):
    models = summary["models"]
    ms = [m for m in models if m in CHEATBENCH_OVERALL and models[m].get("R") is not None]
    fig, axes = plt.subplots(1, 2, figsize=(9.2, 4.0), dpi=160, sharey=True)
    fig.patch.set_facecolor(SURFACE)
    for ax, key, title in ((axes[0], "R", "Physical cell, reference route (pins_R)"),
                           (axes[1], "DP", "Physical cells, tampering routes (D and P, 6 envs)")):
        style(ax)
        for m in ms:
            x = CHEATBENCH_OVERALL[m]
            if key == "R":
                y = models[m]["R"] * 100
            else:
                vals = [v for v in (models[m].get("D"), models[m].get("P")) if v is not None]
                y = 100 * sum(vals) / len(vals) if vals else 0
            ax.scatter([x], [y], s=46, color=SERIES[0], edgecolor=SURFACE, linewidth=1.5, zorder=3)
            ax.annotate(NAMES.get(m, m), (x, y), xytext=(5, 4), textcoords="offset points", fontsize=7.5, color=INK2)
        ax.set_xlim(0, 100)
        ax.set_ylim(-4, 104)
        ax.set_xlabel("CheatBench overall cheating rate (%)", color=INK2, fontsize=9)
        ax.set_title(title, color=INK, fontsize=9.5, loc="left")
    axes[0].set_ylabel("Episodes with a cheating attempt (%)", color=INK2, fontsize=9)
    fig.tight_layout()
    fig.savefig(out, facecolor=SURFACE)
    plt.close(fig)


def heatmap(summary, out):
    cells, models = summary["cells"], summary["models"]
    order = sorted(models, key=lambda m: CHEATBENCH_OVERALL.get(m, 0))
    envs = [e for e in ENVS if any(f"{m}|{e}" in cells for m in order)]
    fig, ax = plt.subplots(figsize=(1.0 * len(envs) + 2.6, 0.5 * len(order) + 1.3), dpi=160)
    fig.patch.set_facecolor(SURFACE)
    ax.set_facecolor(SURFACE)
    for i, m in enumerate(order):
        for j, e in enumerate(envs):
            c = cells.get(f"{m}|{e}")
            if not c:
                continue
            r = c["rate"]
            col = SEQ[min(len(SEQ) - 1, int(r * (len(SEQ) - 1) + 0.5))] if r > 0 else "#f0efec"
            ax.add_patch(plt.Rectangle((j + 0.04, i + 0.04), 0.92, 0.92, color=col, linewidth=0))
            ax.text(j + 0.5, i + 0.5, f"{c['cheat']}/{c['n']}", ha="center", va="center", fontsize=7.5,
                    color="#ffffff" if r >= 0.5 else INK)
    ax.set_xlim(0, len(envs))
    ax.set_ylim(len(order), 0)
    ax.set_xticks([j + 0.5 for j in range(len(envs))])
    ax.set_xticklabels(envs, fontsize=8, color=INK, rotation=30, ha="right")
    ax.set_yticks([i + 0.5 for i in range(len(order))])
    ax.set_yticklabels([NAMES.get(m, m) for m in order], fontsize=8.5, color=INK)
    for s in ax.spines.values():
        s.set_visible(False)
    ax.tick_params(length=0)
    ax.set_title("Cheating attempts per model and environment (episodes)", color=INK, fontsize=10, loc="left")
    fig.tight_layout()
    fig.savefig(out, facecolor=SURFACE)
    plt.close(fig)


if __name__ == "__main__":
    p = Path(sys.argv[1])
    s = json.loads(p.read_text())
    channels(s, p.parent / "fig_channels.png")
    scatter(s, p.parent / "fig_cheatbench.png")
    heatmap(s, p.parent / "fig_heatmap.png")
    print("figures written to", p.parent)
