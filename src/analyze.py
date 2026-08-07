"""Turn scored answers into the tables the paper reports.

    python3 src/analyze.py                 # all tables
    python3 src/analyze.py --agreement     # automatic vs human agreement on the sample

Reads results/scored.jsonl. Prints Markdown tables ready to paste into the paper, and
writes results/tables.md.

Standard library only, deliberately. Every interval here is a bootstrap: resample the
answers with replacement a few thousand times, recompute the statistic, and report the
middle 95% of what comes back. That needs nothing but `random`, and it is easier to
defend out loud than a formula whose assumptions have to be taken on trust.

**Intervals, not p-values.** Per docs/design_decisions.md DD-001 the interaction test is
underpowered by construction, so the honest output is a range. A confidence interval
that spans zero here means "this study could not resolve it", which is a different
statement from "the effect is zero" — the write-up has to keep those apart.
"""

import argparse
import json
import random
import sys
from collections import defaultdict
from pathlib import Path

SCORED_PATH = Path("results/scored.jsonl")
TABLES_PATH = Path("results/tables.md")

BOOTSTRAP_ROUNDS = 5000
RANDOM_SEED = 20260807   # fixed so every run of this script gives the same intervals


def load_scored():
    if not SCORED_PATH.exists():
        print(f"error: {SCORED_PATH} not found — run src/score.py first")
        sys.exit(1)
    return [json.loads(line) for line in SCORED_PATH.read_text(encoding="utf-8").splitlines() if line.strip()]


def scoreable(rows):
    """Only answers that were actually produced. API errors and safety blocks are
    excluded from every rate and reported separately."""
    return [r for r in rows if r["label"] in ("CO", "NA", "IN")]


def rates(rows):
    """CO / NA / IN / CGA / F for a group. Returns None if the group is empty."""
    rows = scoreable(rows)
    if not rows:
        return None
    n = len(rows)
    co = sum(1 for r in rows if r["label"] == "CO") / n
    na = sum(1 for r in rows if r["label"] == "NA") / n
    incorrect = sum(1 for r in rows if r["label"] == "IN") / n
    attempts = sum(1 for r in rows if r["label"] in ("CO", "IN"))
    cga = sum(1 for r in rows if r["label"] == "CO") / attempts if attempts else 0.0
    f = 2 * co * cga / (co + cga) if (co + cga) else 0.0
    return {"n": n, "CO": co, "NA": na, "IN": incorrect, "CGA": cga, "F": f}


def bootstrap_ci(rows, statistic, rounds=BOOTSTRAP_ROUNDS):
    """95% interval for any statistic computed over a list of rows.

    Resample the rows with replacement, recompute, repeat, take the 2.5th and 97.5th
    percentiles. This is the whole method — there is nothing hidden in it.
    """
    rows = scoreable(rows)
    if len(rows) < 2:
        return (None, None)
    rng = random.Random(RANDOM_SEED)
    values = []
    for _ in range(rounds):
        sample = [rows[rng.randrange(len(rows))] for _ in range(len(rows))]
        value = statistic(sample)
        if value is not None:
            values.append(value)
    if not values:
        return (None, None)
    values.sort()
    return (values[int(0.025 * len(values))], values[int(0.975 * len(values))])


def accuracy(rows):
    rows = scoreable(rows)
    return sum(1 for r in rows if r["label"] == "CO") / len(rows) if rows else None


def fmt(value):
    return "—" if value is None else f"{value:.3f}"


def fmt_ci(low, high):
    return "—" if low is None else f"[{low:.3f}, {high:.3f}]"


def group_by(rows, *keys):
    grouped = defaultdict(list)
    for row in rows:
        grouped[tuple(row[k] for k in keys)].append(row)
    return grouped


# ---------------------------------------------------------------------------
# Tables
# ---------------------------------------------------------------------------

def table_headline(rows, out):
    out("## Headline: accuracy, abstention and confident error by model\n")
    out("`IN` is the number that matters: a specific wrong fact, stated as fact.\n")
    out("| model | lang | search | n | CO | NA | IN | CGA | F |")
    out("|---|---|---|---:|---:|---:|---:|---:|---:|")
    for (model, language, mode), group in sorted(group_by(rows, "model_key", "language", "mode").items()):
        r = rates(group)
        if r:
            out(f"| {model} | {language} | {mode} | {r['n']} | {fmt(r['CO'])} | {fmt(r['NA'])} | "
                f"{fmt(r['IN'])} | {fmt(r['CGA'])} | {fmt(r['F'])} |")
    out("")


def table_coverage(rows, out):
    out("## H1 — coverage tier\n")
    out("| model | tier | n | CO | 95% CI | NA | IN |")
    out("|---|---|---:|---:|---|---:|---:|")
    for (model,), model_rows in sorted(group_by(rows, "model_key").items()):
        for tier in ("high", "mid", "low"):
            group = [r for r in model_rows if r["coverage_tier"] == tier]
            r = rates(group)
            if r:
                low, high = bootstrap_ci(group, accuracy)
                out(f"| {model} | {tier} | {r['n']} | {fmt(r['CO'])} | {fmt_ci(low, high)} | "
                    f"{fmt(r['NA'])} | {fmt(r['IN'])} |")
    out("")


def table_volatility(rows, out):
    out("## H2 — fact volatility\n")
    out("| model | volatility | n | CO | 95% CI | NA | IN |")
    out("|---|---|---:|---:|---|---:|---:|")
    for (model,), model_rows in sorted(group_by(rows, "model_key").items()):
        for volatility in ("stable", "annual"):
            group = [r for r in model_rows if r["volatility"] == volatility]
            r = rates(group)
            if r:
                low, high = bootstrap_ci(group, accuracy)
                out(f"| {model} | {volatility} | {r['n']} | {fmt(r['CO'])} | {fmt_ci(low, high)} | "
                    f"{fmt(r['NA'])} | {fmt(r['IN'])} |")
    out("")


def table_interaction(rows, out):
    """The study's main question: do coverage and volatility compound, or just add?

    The quantity is a difference in differences. Within each tier, take the accuracy
    drop caused by volatility (stable minus annual). Then compare that drop in the low
    tier against the high tier. If the drop is bigger where coverage is worse, the two
    effects compound.
    """
    out("## Interaction — coverage x volatility (exploratory, see DD-001)\n")
    out("Per-cell accuracy. The volatility penalty is stable minus annual within a tier.\n")
    out("| model | tier | stable CO | annual CO | penalty | 95% CI |")
    out("|---|---|---:|---:|---:|---|")

    for (model,), model_rows in sorted(group_by(rows, "model_key").items()):
        penalties = {}
        for tier in ("high", "mid", "low"):
            stable = [r for r in model_rows if r["coverage_tier"] == tier and r["volatility"] == "stable"]
            annual = [r for r in model_rows if r["coverage_tier"] == tier and r["volatility"] == "annual"]
            stable_acc, annual_acc = accuracy(stable), accuracy(annual)
            if stable_acc is None or annual_acc is None:
                out(f"| {model} | {tier} | — | — | — | cell empty |")
                continue
            penalty = stable_acc - annual_acc
            penalties[tier] = (stable, annual, penalty)

            def penalty_stat(sample, _stable=stable, _annual=annual):
                rng = random.Random()
                s = [_stable[rng.randrange(len(_stable))] for _ in range(len(_stable))]
                a = [_annual[rng.randrange(len(_annual))] for _ in range(len(_annual))]
                s_acc, a_acc = accuracy(s), accuracy(a)
                return None if s_acc is None or a_acc is None else s_acc - a_acc

            low, high = bootstrap_ci(stable + annual, penalty_stat)
            out(f"| {model} | {tier} | {fmt(stable_acc)} | {fmt(annual_acc)} | {fmt(penalty)} | {fmt_ci(low, high)} |")

        # The interaction term itself: is the volatility penalty larger in low coverage?
        if "low" in penalties and "high" in penalties:
            difference = penalties["low"][2] - penalties["high"][2]
            out(f"\n**{model}: interaction (low-tier penalty minus high-tier penalty) = {difference:+.3f}**\n")
            if abs(difference) < 0.05:
                out("Close to zero: consistent with the two effects being independent — "
                    "coverage failure and staleness are separate mechanisms, and retrieval "
                    "that fixes one need not fix the other. Report as additive-consistent, "
                    "not as proof of additivity.\n")
            elif difference > 0:
                out("Positive: volatile facts about low-coverage institutions are worse than "
                    "the two effects predict separately — a compounding danger zone.\n")
            else:
                out("Negative: check for a floor effect before interpreting. If low-tier "
                    "accuracy is already near zero, volatility has no room to make it worse "
                    "and this number is an artefact, not a finding (DD-002).\n")
    out("")


def table_error_types(rows, out):
    """Stale versus fabricated. This is the analysis that survives a floor effect."""
    out("## Error typology — stale vs fabricated\n")
    out("Among wrong answers, how many repeated a previously-correct value rather than "
        "inventing one. Well defined even when accuracy is at zero.\n")
    out("| model | tier | volatility | wrong | stale | fabricated | stale share |")
    out("|---|---|---|---:|---:|---:|---:|")
    for (model, tier, volatility), group in sorted(group_by(rows, "model_key", "coverage_tier", "volatility").items()):
        wrong = [r for r in group if r["label"] == "IN"]
        if not wrong:
            continue
        stale = sum(1 for r in wrong if r["error_type"] == "stale")
        fabricated = sum(1 for r in wrong if r["error_type"] == "fabricated")
        share = stale / len(wrong)
        out(f"| {model} | {tier} | {volatility} | {len(wrong)} | {stale} | {fabricated} | {share:.1%} |")
    out("")


def table_calibration(rows, out):
    """Does stated confidence track being right? H4's second half."""
    out("## H4 — calibration of stated confidence\n")
    out("| model | stated confidence | n | actually correct |")
    out("|---|---|---:|---:|")
    for (model, confidence), group in sorted(group_by(
        [r for r in rows if r.get("stated_confidence")], "model_key", "stated_confidence"
    ).items()):
        r = rates(group)
        if r:
            out(f"| {model} | {confidence} | {r['n']} | {fmt(r['CO'])} |")
    out("\nThe damaging pattern is a high share of `high` confidence among wrong answers.\n")

    out("| model | wrong answers | of which stated high confidence |")
    out("|---|---:|---:|")
    for (model,), group in sorted(group_by(rows, "model_key").items()):
        wrong = [r for r in group if r["label"] == "IN"]
        if wrong:
            overconfident = sum(1 for r in wrong if r.get("stated_confidence") == "high")
            out(f"| {model} | {len(wrong)} | {overconfident} ({overconfident / len(wrong):.1%}) |")
    out("")


def table_search(rows, out):
    """H5, plus whether the model bothered to search when it could."""
    out("## H5 — effect of web search\n")
    out("| model | tier | no search CO | search CO | change |")
    out("|---|---|---:|---:|---:|")
    for (model,), model_rows in sorted(group_by(rows, "model_key").items()):
        for tier in ("high", "mid", "low"):
            without = [r for r in model_rows if r["coverage_tier"] == tier and r["mode"] == "nosearch"]
            with_search = [r for r in model_rows if r["coverage_tier"] == tier and r["mode"] == "search"]
            a, b = accuracy(without), accuracy(with_search)
            if a is not None and b is not None:
                out(f"| {model} | {tier} | {fmt(a)} | {fmt(b)} | {b - a:+.3f} |")
    out("")

    out("Search availability is not search usage — a model that had the tool and chose "
        "not to use it, then stated a wrong date, is a distinct failure.\n")
    out("| model | answers with search available | at least one search run |")
    out("|---|---:|---:|")
    for (model,), group in sorted(group_by([r for r in rows if r["mode"] == "search"], "model_key").items()):
        used = sum(1 for r in group if r.get("searches_used", 0) > 0)
        out(f"| {model} | {len(group)} | {used} ({used / len(group):.1%}) |")
    out("")


def table_excluded(rows, out):
    """Everything dropped from the rates above, so the exclusions are auditable."""
    excluded = [r for r in rows if r["label"] not in ("CO", "NA", "IN")]
    out("## Excluded answers\n")
    if not excluded:
        out("None.\n")
        return
    out("| model | label | count |")
    out("|---|---|---:|")
    for (model, label), group in sorted(group_by(excluded, "model_key", "label").items()):
        out(f"| {model} | {label} | {len(group)} |")
    out("\n`ERROR` is an API failure, `BLOCKED` a safety-classifier decline, `EMPTY` a "
        "response with no text. None of these are the model judging its own knowledge, "
        "so counting them as wrong answers would overstate the error rate.\n")


def report_agreement():
    """How often the automatic scorer disagrees with a human on the review sample.

    This number belongs in the paper. Without it every accuracy figure rests on an
    unmeasured assumption about the scorer.
    """
    path = Path("results/handcheck_sample.jsonl")
    if not path.exists():
        print("error: results/handcheck_sample.jsonl not found — run: python3 src/score.py --sample 50")
        return 1

    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    checked = [r for r in rows if r.get("human_label")]
    if not checked:
        print(f"none of the {len(rows)} sampled answers have human_label filled in yet")
        return 1

    agree = sum(1 for r in checked if r["human_label"].strip().upper() == r["automatic_label"])
    print(f"label agreement: {agree}/{len(checked)} = {agree / len(checked):.1%}")

    disagreements = [r for r in checked if r["human_label"].strip().upper() != r["automatic_label"]]
    if disagreements:
        print(f"\n{len(disagreements)} disagreement(s) — read these, they show what the scorer gets wrong:")
        for row in disagreements:
            print(f"\n  {row['item_id']} ({row['model']}, {row['language']}, {row['mode']})")
            print(f"    gold:      {row['gold_answer']}")
            print(f"    model:     {row['model_answer'][:100]}")
            print(f"    automatic: {row['automatic_label']}   human: {row['human_label']}")

    typed = [r for r in checked if r["automatic_error_type"] and r.get("human_error_type")]
    if typed:
        agree_type = sum(1 for r in typed if r["human_error_type"].strip().lower() == r["automatic_error_type"])
        print(f"\nstale/fabricated agreement: {agree_type}/{len(typed)} = {agree_type / len(typed):.1%}")
    return 0


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--agreement", action="store_true",
                        help="report automatic vs human agreement instead of the tables")
    args = parser.parse_args()

    if args.agreement:
        return report_agreement()

    rows = load_scored()
    lines = []

    def out(text):
        print(text)
        lines.append(text)

    out(f"# Results\n\n{len(rows)} scored answers.\n")
    table_headline(rows, out)
    table_coverage(rows, out)
    table_volatility(rows, out)
    table_interaction(rows, out)
    table_error_types(rows, out)
    table_calibration(rows, out)
    table_search(rows, out)
    table_excluded(rows, out)

    TABLES_PATH.write_text("\n".join(lines), encoding="utf-8")
    print(f"\nwritten to {TABLES_PATH}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
