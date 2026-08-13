"""Score raw model answers into per-answer labels.

    python3 src/score.py                      # score everything in results/raw/
    python3 src/score.py --sample 50          # also write a hand-check sample

Reads results/raw/*.jsonl, writes results/scored.jsonl. Never touches results/raw/.

Metric vocabulary is borrowed from MSQA (arXiv:2607.00724) rather than invented, so
the numbers are comparable to a current benchmark:

    CO   correct
    NA   non-committal — an explicit refusal to answer
    IN   incorrect and specific — a concrete wrong fact stated as fact
    CGA  correctness given attempt = CO / (CO + IN); accuracy when the model chose to answer
    F    harmonic mean of CO and CGA; rewards being right, penalises both guessing and
         refusing everything

The CO/NA/IN split is the point of the study. A model that says "I don't know" behaves
correctly. A model that invents a deadline causes harm. A metric that averages the two
into one accuracy number hides the finding.

IN answers are split further, which is this project's own addition (see
docs/design_decisions.md DD-003):

    stale       the wrong answer matches a previously-correct value — the model is
                behind, not inventing
    fabricated  the wrong answer matches no value the fact has ever held
"""

import argparse
import json
import random
import re
import sys
import unicodedata
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from qualifiers import families_for, family_of  # noqa: E402

RAW_DIR = Path("results/raw")
SCORED_PATH = Path("results/scored.jsonl")

# Phrases that count as an explicit refusal. The prompt asks for an exact string, but
# models paraphrase, so a modest list of equivalents is needed. Anything beyond this
# list is treated as an attempt to answer — the conservative direction, since it can
# only move an answer out of NA and into CO or IN.
ABSTENTION_MARKERS = [
    "i don't know", "i do not know", "i dont know",
    "не знаю",
    "i'm not sure", "i am not sure", "not certain", "unable to determine",
    "cannot determine", "can't determine",
    "i don't have access to", "i do not have access to",
    "no reliable information", "unable to verify", "cannot verify",
]

MONTHS = {
    "january": 1, "february": 2, "march": 3, "april": 4, "may": 5, "june": 6,
    "july": 7, "august": 8, "september": 9, "october": 10, "november": 11, "december": 12,
    "jan": 1, "feb": 2, "mar": 3, "apr": 4, "jun": 6, "jul": 7,
    "aug": 8, "sep": 9, "sept": 9, "oct": 10, "nov": 11, "dec": 12,
    "января": 1, "февраля": 2, "марта": 3, "апреля": 4, "мая": 5, "июня": 6,
    "июля": 7, "августа": 8, "сентября": 9, "октября": 10, "ноября": 11, "декабря": 12,
    "январь": 1, "февраль": 2, "март": 3, "апрель": 4, "май": 5, "июнь": 6,
    "июль": 7, "август": 8, "сентябрь": 9, "октябрь": 10, "ноябрь": 11, "декабрь": 12,
}

CURRENCY_WORDS = {
    "usd": "usd", "$": "usd", "dollars": "usd", "dollar": "usd", "долларов": "usd", "доллар": "usd",
    "eur": "eur", "€": "eur", "euros": "eur", "euro": "eur", "евро": "eur",
    "gbp": "gbp", "£": "gbp", "pounds": "gbp", "pound": "gbp", "фунтов": "gbp",
    "aed": "aed", "dirhams": "aed", "dirham": "aed", "дирхам": "aed", "дирхамов": "aed",
}


def strip_confidence(text):
    """Remove the trailing CONFIDENCE: line and return (answer, confidence)."""
    match = re.search(r"CONFIDENCE:\s*(high|medium|low)", text, re.IGNORECASE)
    confidence = match.group(1).lower() if match else None
    cleaned = re.sub(r"CONFIDENCE:\s*(high|medium|low)", "", text, flags=re.IGNORECASE)
    return cleaned.strip(), confidence


# Small written numbers, for durations and counts. Pages write "nine-month course" and
# "one-calendar-year"; models overwhelmingly answer in digits. Both are the same fact,
# and a scorer that cannot see that marks a correct answer wrong — observed three times
# in the first 24 pilot answers.
WORD_NUMBERS = {
    "one": "1", "two": "2", "three": "3", "four": "4", "five": "5", "six": "6",
    "seven": "7", "eight": "8", "nine": "9", "ten": "10", "eleven": "11", "twelve": "12",
    "один": "1", "два": "2", "две": "2", "три": "3", "четыре": "4", "пять": "5",
    "шесть": "6", "семь": "7", "восемь": "8", "девять": "9", "десять": "10",
}


def normalise(text):
    """Reduce a string to a comparable form: lowercase, no accents, no punctuation.

    Hyphens become spaces — "first-class honours" and "first class honours" are one
    wording, not two — and small written numbers become digits, so "nine-month" can meet
    "9 months". Both changes apply to answer and gold alike, so nothing is asymmetric.
    """
    text = unicodedata.normalize("NFKD", text.lower())
    text = "".join(c for c in text if not unicodedata.combining(c))
    text = re.sub(r"[-–—]", " ", text)
    text = re.sub(r"[^\w\s./]", " ", text)
    words = [WORD_NUMBERS.get(w, w) for w in text.split()]
    return " ".join(words)


def extract_dates(text):
    """Find dates and return them as (year, month, day) tuples.

    Handles the forms models actually produce: "1 November 2026", "November 1, 2026",
    "01.11.2026", "2026-11-01", "1 ноября 2026". Comparing tuples rather than strings
    is what stops "November 1st, 2026" from being scored wrong against "1 November 2026".
    """
    found = set()
    lowered = text.lower()

    # 1 November 2026 / 1 ноября 2026
    for day, month_name, year in re.findall(
        r"\b(\d{1,2})(?:st|nd|rd|th)?\s+([a-zа-я]+),?\s+(\d{4})\b", lowered
    ):
        if month_name in MONTHS:
            found.add((int(year), MONTHS[month_name], int(day)))

    # November 1, 2026
    for month_name, day, year in re.findall(
        r"\b([a-zа-я]+)\s+(\d{1,2})(?:st|nd|rd|th)?,?\s+(\d{4})\b", lowered
    ):
        if month_name in MONTHS:
            found.add((int(year), MONTHS[month_name], int(day)))

    # 2026-11-01
    for year, month, day in re.findall(r"\b(\d{4})-(\d{1,2})-(\d{1,2})\b", lowered):
        found.add((int(year), int(month), int(day)))

    # 01.11.2026 and 01/11/2026 — day-first, the convention on the sources used here.
    for day, month, year in re.findall(r"\b(\d{1,2})[./](\d{1,2})[./](\d{4})\b", lowered):
        if int(month) <= 12:
            found.add((int(year), int(month), int(day)))

    return found


def extract_money(text):
    """Find monetary amounts as (currency_or_None, amount) pairs.

    Thousands separators are stripped so "$61,676" and "61676 USD" match. Currency is
    recorded when it can be identified, so a figure in the wrong currency is not
    scored as correct.
    """
    found = set()
    lowered = text.lower()

    for symbol, amount in re.findall(r"([$€£])\s?([\d][\d,\s.]*)", lowered):
        value = to_number(amount)
        if value is not None:
            found.add((CURRENCY_WORDS.get(symbol), value))

    for amount, word in re.findall(r"([\d][\d,\s.]*)\s*([a-zа-я]{3,10})\b", lowered):
        if word in CURRENCY_WORDS:
            value = to_number(amount)
            if value is not None:
                found.add((CURRENCY_WORDS[word], value))

    return found


def to_number(raw):
    """Parse a number written with thousands separators. Returns None if not a number."""
    cleaned = raw.replace(",", "").replace(" ", "").rstrip(".")
    if cleaned.count(".") > 1:
        cleaned = cleaned.replace(".", "")
    try:
        value = float(cleaned)
    except ValueError:
        return None
    return int(value) if value == int(value) else value


def extract_numbers(text):
    """Bare numbers, for test scores and durations. Years are excluded — a year is
    almost always part of a date, and treating it as a score creates false matches."""
    values = set()
    for raw in re.findall(r"\b\d+(?:\.\d+)?\b", text):
        value = to_number(raw)
        if value is not None and not (1900 <= value <= 2100):
            values.add(value)
    return values


def matches(answer, target):
    """Does `answer` contain the fact stated in `target`?

    Tries the structured comparisons first (dates, money, numbers) and falls back to
    substring matching. The order matters: a date comparison understands that two
    differently formatted strings are the same fact, which a substring test cannot.
    """
    if not target:
        return False

    answer_norm, target_norm = normalise(answer), normalise(target)
    if not target_norm:
        return False

    target_dates = extract_dates(target)
    if target_dates:
        return bool(target_dates & extract_dates(answer))

    target_money = extract_money(target)
    if target_money:
        answer_money = extract_money(answer)
        # An amount with no currency named still counts, provided the figure matches:
        # models routinely drop the unit when the question already established it.
        for currency, amount in target_money:
            for answer_currency, answer_amount in answer_money:
                if amount == answer_amount and (answer_currency is None or answer_currency == currency):
                    return True
        return amount_in_bare_numbers(target_money, answer)

    # Numbers are pulled from the *normalised* strings, where "nine-month" has already
    # become "9 month" — on the raw string a spelled-out number is invisible to \d.
    target_numbers = extract_numbers(target_norm)
    if target_numbers and len(target_norm.split()) <= 3:
        return bool(target_numbers & extract_numbers(answer_norm))

    return target_norm in answer_norm


def amount_in_bare_numbers(target_money, answer):
    answer_numbers = extract_numbers(answer)
    return any(amount in answer_numbers for _, amount in target_money)


def qualifier_agrees(answer, item, target):
    """Does the answer carry the same period, or the same test, as `target`?

    Items whose value is meaningless alone (DD-008) store the two halves separately. The
    numeric comparison alone would mark "$33,360 per year" correct against a gold answer
    of "$33,360 per term", which is exactly the mistake a benchmark about factual
    reliability should be catching.

    Checked against the target that matched, not against the gold answer, because the
    accepted variants can carry a different qualifier and still be right. TU Delft states
    "TOEFL iBT 90, or IELTS 6.5": both answer the question. With the gold answer's
    qualifier used for every comparison, a model saying "IELTS 6.5" would match the
    variant on its number and then fail on the test name, and be scored incorrect for
    giving one of the two answers the university itself publishes.

    An answer that names no period or test at all is not credited: the question asks for
    it in so many words.
    """
    if not item.get("answer_parts"):
        return True
    families = families_for(item["fact_type"])
    target_family = family_of(target, families)
    if target_family is None:
        # Worded in a way these tables do not cover. Require the words themselves rather
        # than silently waiving the requirement.
        qualifier = (item["answer_parts"] or {}).get("qualifier", "")
        return bool(qualifier) and normalise(qualifier) in normalise(answer)
    return family_of(answer, families) == target_family


def is_abstention(answer):
    if not answer.strip():
        return False   # an empty answer is a failure to respond, not a refusal
    lowered = answer.lower()
    return any(marker in lowered for marker in ABSTENTION_MARKERS)


def score_one(row, item):
    """Label one raw answer. Returns the row plus label, error_type and confidence."""
    answer, confidence = strip_confidence(row.get("answer_text", "") or "")

    if row.get("error"):
        label, error_type = "ERROR", None
    elif row.get("stop_reason") == "refusal":
        # A safety-classifier decline is not the model judging its own knowledge, so it
        # is kept out of NA — folding it in would inflate the abstention rate.
        label, error_type = "BLOCKED", None
    elif not answer.strip():
        label, error_type = "EMPTY", None
    else:
        # Correctness is judged before abstention, not after. Gemma prefixes its answers
        # with a scratchpad that restates the prompt's instructions — including the
        # literal words "reply with exactly: I DON'T KNOW" — and an abstention check
        # that runs first reads that quotation and files a correct answer as a refusal;
        # 93 of 94 pilot answers were mislabelled that way. A response that commits to
        # the right fact is an attempt, whatever hedging surrounds it, and the same rule
        # is applied to every model symmetrically.
        targets = [item["gold_answer"], *item.get("acceptable_variants", [])]
        if any(matches(answer, target) and qualifier_agrees(answer, item, target)
               for target in targets):
            label, error_type = "CO", None
        elif is_abstention(answer):
            label, error_type = "NA", None
        else:
            label = "IN"
            prior = item.get("prior_year_answer")
            error_type = "stale" if prior and matches(answer, prior) else "fabricated"

    return {
        **row,
        "label": label,
        "error_type": error_type,
        "stated_confidence": confidence,
        "answer_clean": answer,
        # Carried through so analyze.py can group without re-reading the benchmark.
        "coverage_tier": item["coverage_tier"],
        "volatility": item["volatility"],
        "fact_type": item["fact_type"],
        "university": item["university"],
    }


def summarise(rows):
    """Compute CO/NA/IN/CGA/F for a set of scored rows."""
    counts = defaultdict(int)
    for row in rows:
        counts[row["label"]] += 1

    # Rows that never produced a usable answer are excluded from the denominator and
    # reported separately; counting an API failure as a wrong answer would be a lie.
    scoreable = counts["CO"] + counts["NA"] + counts["IN"]
    if scoreable == 0:
        return None

    co = counts["CO"] / scoreable
    na = counts["NA"] / scoreable
    incorrect = counts["IN"] / scoreable
    attempts = counts["CO"] + counts["IN"]
    cga = counts["CO"] / attempts if attempts else 0.0
    f = 2 * co * cga / (co + cga) if (co + cga) else 0.0

    stale = sum(1 for r in rows if r["error_type"] == "stale")
    fabricated = sum(1 for r in rows if r["error_type"] == "fabricated")

    return {
        "n": scoreable,
        "CO": co, "NA": na, "IN": incorrect, "CGA": cga, "F": f,
        "stale": stale,
        "fabricated": fabricated,
        "stale_share_of_errors": stale / (stale + fabricated) if (stale + fabricated) else None,
        "excluded": counts["ERROR"] + counts["EMPTY"] + counts["BLOCKED"],
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--benchmark", default="data/benchmark.jsonl")
    parser.add_argument("--sample", type=int, metavar="N",
                        help="also write results/handcheck_sample.jsonl with N random answers "
                             "for manual review — the automatic-vs-human agreement number")
    args = parser.parse_args()

    benchmark = {}
    for line in Path(args.benchmark).read_text(encoding="utf-8").splitlines():
        if line.strip():
            item = json.loads(line)
            benchmark[item["id"]] = item

    scored = []
    for path in sorted(RAW_DIR.glob("*.jsonl")):
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            row = json.loads(line)
            item = benchmark.get(row["item_id"])
            if item is None:
                print(f"warning: {row['item_id']} is in results but not in the benchmark; skipped")
                continue
            scored.append(score_one(row, item))

    SCORED_PATH.parent.mkdir(parents=True, exist_ok=True)
    with SCORED_PATH.open("w", encoding="utf-8") as out:
        for row in scored:
            out.write(json.dumps(row, ensure_ascii=False) + "\n")
    print(f"scored {len(scored)} answers -> {SCORED_PATH}")

    overall = summarise(scored)
    if overall:
        print(f"\noverall: CO={overall['CO']:.3f}  NA={overall['NA']:.3f}  IN={overall['IN']:.3f}  "
              f"CGA={overall['CGA']:.3f}  F={overall['F']:.3f}  (n={overall['n']}, excluded={overall['excluded']})")
        if overall["stale_share_of_errors"] is not None:
            print(f"of the wrong answers, {overall['stale_share_of_errors']:.1%} were stale "
                  f"({overall['stale']} stale / {overall['fabricated']} fabricated)")

    if args.sample:
        # Manual review of a random sample is how the paper reports how often the
        # automatic scorer disagrees with a human. Without that number, every accuracy
        # figure rests on an unmeasured assumption.
        random.seed(20260807)   # fixed so the sample is reproducible
        chosen = random.sample(scored, min(args.sample, len(scored)))
        path = Path("results/handcheck_sample.jsonl")
        with path.open("w", encoding="utf-8") as out:
            for row in chosen:
                out.write(json.dumps({
                    "item_id": row["item_id"], "model": row["model"],
                    "language": row["language"], "mode": row["mode"],
                    "question": row["question"],
                    "gold_answer": benchmark[row["item_id"]]["gold_answer"],
                    "prior_year_answer": benchmark[row["item_id"]].get("prior_year_answer"),
                    "model_answer": row["answer_clean"],
                    "automatic_label": row["label"],
                    "automatic_error_type": row["error_type"],
                    "human_label": "",       # fill in by hand: CO / NA / IN
                    "human_error_type": "",  # fill in by hand for IN: stale / fabricated
                }, ensure_ascii=False) + "\n")
        print(f"\nwrote {len(chosen)} answers to {path} for manual review")
        print("fill in human_label by hand, then run: python3 src/analyze.py --agreement")

    return 0


if __name__ == "__main__":
    sys.exit(main())
