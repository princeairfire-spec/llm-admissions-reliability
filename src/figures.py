"""Draw the paper's figures as SVG.

    python3 src/figures.py            # writes results/figures/*.svg

Reads results/scored.jsonl. Nothing is installed to run this: an SVG file is XML text,
so the standard library is enough. The output is vector, which is what a paper wants —
it stays sharp at any size and LaTeX takes it directly.

Three figures, in the order they should appear in the paper:

    fig1_outcomes.svg      what happens when a model is asked: right, refused, or
                           confidently wrong. The paper's headline.
    fig2_interaction.svg   accuracy by coverage tier and volatility. The study's main
                           question, drawn so the reader can see whether the lines
                           diverge (effects compound) or stay parallel (independent).
    fig3_errors.svg        of the wrong answers, how many were stale rather than
                           invented. The contribution nobody else has measured.
"""

import json
import sys
from collections import defaultdict
from pathlib import Path

SCORED_PATH = Path("results/scored.jsonl")
OUT_DIR = Path("results/figures")

# A restrained palette that survives greyscale printing, which reviewers still do.
# Correct is calm, refusal is neutral, confident error is the one that should catch
# the eye — the figure should carry the argument before the caption is read.
CORRECT, ABSTAIN, WRONG = "#2a6f4e", "#9aa0a6", "#b3402f"
TIER_COLOURS = {"high": "#1f4e79", "mid": "#3d8bbf", "low": "#c25b3a"}
INK, GRID = "#1a1a1a", "#d8d8d8"
FONT = "font-family='Helvetica,Arial,sans-serif'"


def escape(text):
    return str(text).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


class Canvas:
    """A very small SVG writer. Every method appends one element; `render` wraps them.

    Y coordinates in SVG grow downward, which is the opposite of a chart axis. All the
    plotting code below converts once, at the point of use, rather than fighting it.
    """

    def __init__(self, width, height):
        self.width, self.height, self.parts = width, height, []

    def rect(self, x, y, w, h, fill, opacity=1.0):
        if h <= 0 or w <= 0:
            return
        self.parts.append(
            f"<rect x='{x:.1f}' y='{y:.1f}' width='{w:.1f}' height='{h:.1f}' "
            f"fill='{fill}' opacity='{opacity}'/>"
        )

    def line(self, x1, y1, x2, y2, stroke=GRID, width=1, dash=None):
        d = f" stroke-dasharray='{dash}'" if dash else ""
        self.parts.append(
            f"<line x1='{x1:.1f}' y1='{y1:.1f}' x2='{x2:.1f}' y2='{y2:.1f}' "
            f"stroke='{stroke}' stroke-width='{width}'{d}/>"
        )

    def polyline(self, points, stroke, width=2.5):
        coords = " ".join(f"{x:.1f},{y:.1f}" for x, y in points)
        self.parts.append(
            f"<polyline points='{coords}' fill='none' stroke='{stroke}' "
            f"stroke-width='{width}' stroke-linejoin='round'/>"
        )

    def circle(self, x, y, r, fill):
        self.parts.append(f"<circle cx='{x:.1f}' cy='{y:.1f}' r='{r}' fill='{fill}'/>")

    def text(self, x, y, content, size=11, anchor="start", fill=INK, weight="normal"):
        self.parts.append(
            f"<text x='{x:.1f}' y='{y:.1f}' {FONT} font-size='{size}' "
            f"text-anchor='{anchor}' fill='{fill}' font-weight='{weight}'>{escape(content)}</text>"
        )

    def render(self):
        return (
            f"<svg xmlns='http://www.w3.org/2000/svg' width='{self.width}' "
            f"height='{self.height}' viewBox='0 0 {self.width} {self.height}'>"
            f"<rect width='100%' height='100%' fill='white'/>"
            + "".join(self.parts) + "</svg>"
        )


def load():
    if not SCORED_PATH.exists():
        print(f"error: {SCORED_PATH} not found — run src/score.py first")
        sys.exit(1)
    rows = [json.loads(l) for l in SCORED_PATH.read_text(encoding="utf-8").splitlines() if l.strip()]
    return [r for r in rows if r["label"] in ("CO", "NA", "IN")]


def shares(rows):
    """Fractions of correct / abstained / wrong. Returns None for an empty group."""
    if not rows:
        return None
    n = len(rows)
    return (
        sum(1 for r in rows if r["label"] == "CO") / n,
        sum(1 for r in rows if r["label"] == "NA") / n,
        sum(1 for r in rows if r["label"] == "IN") / n,
    )


def accuracy(rows):
    return sum(1 for r in rows if r["label"] == "CO") / len(rows) if rows else None


def axis(canvas, left, top, plot_w, plot_h, label):
    """Y axis from 0 to 1 with gridlines every 0.2."""
    for step in range(6):
        value = step / 5
        y = top + plot_h - value * plot_h
        canvas.line(left, y, left + plot_w, y, GRID)
        canvas.text(left - 8, y + 4, f"{value:.1f}", size=10, anchor="end", fill="#666")
    canvas.line(left, top, left, top + plot_h, INK, 1.2)
    canvas.line(left, top + plot_h, left + plot_w, top + plot_h, INK, 1.2)
    canvas.text(left - 40, top + plot_h / 2, label, size=11, anchor="middle")


# ---------------------------------------------------------------------------

def fig_outcomes(rows, path):
    """Stacked bars: correct / abstained / confidently wrong, per model and condition."""
    groups = defaultdict(list)
    for r in rows:
        groups[(r["model_key"], r["language"], r["mode"])].append(r)
    keys = sorted(groups)

    left, top, plot_h = 70, 60, 300
    bar_w, gap = 46, 22
    plot_w = max(420, len(keys) * (bar_w + gap) + gap)
    canvas = Canvas(left + plot_w + 40, top + plot_h + 130)

    canvas.text(left - 40, 28, "What happens when a model is asked an admissions question",
                size=14, weight="bold")
    canvas.text(left - 40, 46, "Share of answers. Red is a specific wrong fact stated as fact.",
                size=11, fill="#555")
    axis(canvas, left, top, plot_w, plot_h, "share")

    for index, key in enumerate(keys):
        s = shares(groups[key])
        if not s:
            continue
        correct, abstain, wrong = s
        x = left + gap + index * (bar_w + gap)
        y = top + plot_h
        for value, colour in ((correct, CORRECT), (abstain, ABSTAIN), (wrong, WRONG)):
            h = value * plot_h
            y -= h
            canvas.rect(x, y, bar_w, h, colour)

        model, language, mode = key
        canvas.text(x + bar_w / 2, top + plot_h + 16, model, size=10, anchor="middle")
        canvas.text(x + bar_w / 2, top + plot_h + 29, f"{language}/{mode[:6]}", size=9,
                    anchor="middle", fill="#666")
        if correct > 0.08:
            canvas.text(x + bar_w / 2, top + plot_h - correct * plot_h / 2 + 4,
                        f"{correct:.0%}", size=10, anchor="middle", fill="white", weight="bold")

    legend_y = top + plot_h + 62
    for offset, (colour, label) in enumerate((
        (CORRECT, "correct"), (ABSTAIN, "said it did not know"), (WRONG, "confidently wrong"),
    )):
        x = left + offset * 165
        canvas.rect(x, legend_y, 12, 12, colour)
        canvas.text(x + 18, legend_y + 11, label, size=11)
    path.write_text(canvas.render(), encoding="utf-8")


def fig_interaction(rows, path):
    """The main question, drawn as two lines per model.

    One line for stable facts, one for volatile, across the three coverage tiers. If the
    lines stay parallel, the two effects are independent. If the gap widens toward the
    low-coverage end, they compound — which is exactly what the study asks.
    """
    models = sorted({r["model_key"] for r in rows})
    tiers = ["high", "mid", "low"]
    panel_w, plot_h, top = 240, 260, 72
    left = 62
    canvas = Canvas(left + len(models) * (panel_w + 34) + 30, top + plot_h + 120)

    canvas.text(left - 34, 28, "Does low coverage make volatile facts worse than expected?",
                size=14, weight="bold")
    canvas.text(left - 34, 46, "Parallel lines mean the two effects are independent; "
                               "a widening gap means they compound.", size=11, fill="#555")

    for m_index, model in enumerate(models):
        px = left + m_index * (panel_w + 34)
        for step in range(6):
            y = top + plot_h - (step / 5) * plot_h
            canvas.line(px, y, px + panel_w, y, GRID)
            if m_index == 0:
                canvas.text(px - 8, y + 4, f"{step / 5:.1f}", size=10, anchor="end", fill="#666")
        canvas.line(px, top, px, top + plot_h, INK, 1.2)
        canvas.line(px, top + plot_h, px + panel_w, top + plot_h, INK, 1.2)
        canvas.text(px + panel_w / 2, top - 12, model, size=12, anchor="middle", weight="bold")

        step_x = panel_w / (len(tiers) + 1)
        for t_index, tier in enumerate(tiers):
            canvas.text(px + step_x * (t_index + 1), top + plot_h + 18, tier,
                        size=10, anchor="middle")

        for volatility, dash in (("stable", None), ("annual", "5,4")):
            points = []
            for t_index, tier in enumerate(tiers):
                group = [r for r in rows if r["model_key"] == model
                         and r["coverage_tier"] == tier and r["volatility"] == volatility]
                a = accuracy(group)
                if a is None:
                    continue
                points.append((px + step_x * (t_index + 1), top + plot_h - a * plot_h))
            if len(points) > 1:
                colour = INK if volatility == "stable" else WRONG
                coords = " ".join(f"{x:.1f},{y:.1f}" for x, y in points)
                canvas.parts.append(
                    f"<polyline points='{coords}' fill='none' stroke='{colour}' "
                    f"stroke-width='2.5'" + (f" stroke-dasharray='{dash}'" if dash else "") + "/>"
                )
                for x, y in points:
                    canvas.circle(x, y, 4, colour)

        if m_index == 0:
            canvas.text(left - 46, top + plot_h / 2, "accuracy", size=11, anchor="middle")

    legend_y = top + plot_h + 54
    canvas.line(left, legend_y, left + 30, legend_y, INK, 2.5)
    canvas.text(left + 38, legend_y + 4, "stable facts", size=11)
    canvas.line(left + 150, legend_y, left + 180, legend_y, WRONG, 2.5, dash="5,4")
    canvas.text(left + 188, legend_y + 4, "facts that change every cycle", size=11)
    path.write_text(canvas.render(), encoding="utf-8")


def fig_errors(rows, path):
    """Of the wrong answers, how many repeated last year's value rather than inventing.

    This is the figure that still works if accuracy collapses to zero, because it is a
    composition of the errors rather than a rate of them.
    """
    wrong = [r for r in rows if r["label"] == "IN"]
    if not wrong:
        return
    groups = defaultdict(list)
    for r in wrong:
        groups[(r["model_key"], r["coverage_tier"])].append(r)
    keys = sorted(groups)

    left, top, plot_h = 70, 62, 260
    bar_w, gap = 40, 20
    plot_w = max(420, len(keys) * (bar_w + gap) + gap)
    canvas = Canvas(left + plot_w + 40, top + plot_h + 120)

    canvas.text(left - 40, 28, "Are wrong answers stale, or invented?", size=14, weight="bold")
    canvas.text(left - 40, 46, "Composition of incorrect answers only. Stale = a value that "
                               "was correct in an earlier cycle.", size=11, fill="#555")
    axis(canvas, left, top, plot_w, plot_h, "share of errors")

    STALE, FABRICATED = "#7b5aa6", "#d99a2b"
    for index, key in enumerate(keys):
        group = groups[key]
        stale = sum(1 for r in group if r["error_type"] == "stale") / len(group)
        x = left + gap + index * (bar_w + gap)
        canvas.rect(x, top + plot_h - stale * plot_h, bar_w, stale * plot_h, STALE)
        canvas.rect(x, top, bar_w, plot_h - stale * plot_h, FABRICATED)
        model, tier = key
        canvas.text(x + bar_w / 2, top + plot_h + 16, tier, size=10, anchor="middle")
        canvas.text(x + bar_w / 2, top + plot_h + 29, model, size=9, anchor="middle", fill="#666")
        canvas.text(x + bar_w / 2, top + plot_h + 42, f"n={len(group)}", size=8,
                    anchor="middle", fill="#999")

    legend_y = top + plot_h + 66
    for offset, (colour, label) in enumerate(((STALE, "stale — was correct before"),
                                              (FABRICATED, "fabricated — never correct"))):
        x = left + offset * 210
        canvas.rect(x, legend_y, 12, 12, colour)
        canvas.text(x + 18, legend_y + 11, label, size=11)
    path.write_text(canvas.render(), encoding="utf-8")


def main():
    rows = load()
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    fig_outcomes(rows, OUT_DIR / "fig1_outcomes.svg")
    fig_interaction(rows, OUT_DIR / "fig2_interaction.svg")
    fig_errors(rows, OUT_DIR / "fig3_errors.svg")
    for path in sorted(OUT_DIR.glob("*.svg")):
        print(f"  {path}  ({path.stat().st_size:,} bytes)")
    print("\nOpen them in a browser to check. LaTeX: \\includegraphics{fig2_interaction.svg} "
          "via svg package, or convert once with rsvg-convert / Inkscape if the venue wants PDF.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
