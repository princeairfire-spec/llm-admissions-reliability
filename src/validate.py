"""Validate the benchmark file: schema, cell balance, duplicates.

Run this after every collection session. It is deliberately written with the standard
library only and with every check spelled out, so that each rule is visible in the
source rather than hidden inside a validation library.

    python3 src/validate.py data/benchmark.jsonl

Exit code 0 means the file is clean; 1 means at least one error was found. Errors block
the dataset. Warnings do not, but they are the things that quietly ruin a study, so
read them.
"""

import json
import re
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from extract import normalise  # noqa: E402

# ---------------------------------------------------------------------------
# The rules. These mirror data/schema.json. If you change one, change both.
# ---------------------------------------------------------------------------

REQUIRED_FIELDS = [
    "id", "university", "country", "coverage_tier",
    "question_en", "question_ru", "fact_type", "volatility",
    "gold_answer", "acceptable_variants", "prior_year_answer",
    "source_url", "source_quote", "snapshot_path", "date_accessed",
    "verified_by", "verification_round", "notes",
]

OPTIONAL_FIELDS = ["round1_gold_answer", "answer_parts", "cycle_quoted",
                   "prior_source"]

ALLOWED_VALUES = {
    "coverage_tier": {"high", "mid", "low"},
    "volatility": {"annual", "stable"},
    "fact_type": {
        "deadline", "test_requirement", "tuition",
        "document_list", "program_structure", "eligibility",
    },
}

ID_PATTERN = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")
COUNTRY_PATTERN = re.compile(r"^[A-Z]{2}$")
DATE_PATTERN = re.compile(r"^\d{4}-\d{2}-\d{2}$")

# Below this many items in a coverage_tier x volatility cell, the interaction test in
# docs/design_decisions.md DD-001 has no chance of resolving. See docs/budget.md.
MIN_ITEMS_PER_CELL = 30


def load_items(path):
    """Read a JSON Lines file: one JSON object per line, blank lines skipped.

    Returns (items, errors). A line that is not valid JSON is reported and skipped
    rather than raising, so one bad line does not hide the rest of the file.
    """
    items, errors = [], []
    for line_number, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not raw.strip():
            continue
        try:
            items.append((line_number, json.loads(raw)))
        except json.JSONDecodeError as exc:
            errors.append(f"line {line_number}: not valid JSON ({exc.msg})")
    return items, errors


def check_fields(line_number, item):
    """Check one item against the schema. Returns a list of error strings."""
    errors = []
    where = f"line {line_number} (id={item.get('id', '?')})"

    for field in REQUIRED_FIELDS:
        if field not in item:
            errors.append(f"{where}: missing required field '{field}'")

    known = set(REQUIRED_FIELDS) | set(OPTIONAL_FIELDS)
    for field in item:
        if field not in known:
            errors.append(f"{where}: unknown field '{field}' (typo, or schema.json is out of date)")

    # Enumerated fields: a typo here silently moves an item into the wrong cell,
    # which is worse than a crash, so it is an error rather than a warning.
    for field, allowed in ALLOWED_VALUES.items():
        if field in item and item[field] not in allowed:
            errors.append(f"{where}: {field}={item[field]!r} is not one of {sorted(allowed)}")

    if "id" in item and not ID_PATTERN.match(str(item["id"])):
        errors.append(f"{where}: id must be lowercase-hyphenated")
    if "country" in item and not COUNTRY_PATTERN.match(str(item["country"])):
        errors.append(f"{where}: country must be a 2-letter uppercase code, got {item['country']!r}")
    if "date_accessed" in item and not DATE_PATTERN.match(str(item["date_accessed"])):
        errors.append(f"{where}: date_accessed must be YYYY-MM-DD, got {item['date_accessed']!r}")
    if "source_url" in item and not str(item["source_url"]).startswith("https://"):
        errors.append(f"{where}: source_url must start with https://")
    if "acceptable_variants" in item and not isinstance(item["acceptable_variants"], list):
        errors.append(f"{where}: acceptable_variants must be a list (use [] if there are none)")
    if "verification_round" in item and item["verification_round"] not in (1, 2):
        errors.append(f"{where}: verification_round must be 1 or 2")

    # The snapshot is the evidence for the gold answer. A path that points at nothing
    # means the claim cannot be checked by anyone, including the author in three months.
    if "snapshot_path" in item:
        snapshot = Path(item["snapshot_path"])
        if not str(snapshot).startswith("data/snapshots/"):
            errors.append(f"{where}: snapshot_path must be under data/snapshots/")
        elif not snapshot.exists():
            errors.append(f"{where}: snapshot file does not exist: {snapshot}")

    # A stable fact cannot have had a different value last year — that is what stable
    # means. If this fires, either volatility or prior_year_answer is wrong.
    if item.get("volatility") == "stable" and item.get("prior_year_answer") not in (None, ""):
        errors.append(f"{where}: volatility=stable but prior_year_answer is set — one of the two is wrong")

    # A gold answer that equals last year's value means nothing changed, so the item is
    # not actually testing volatility, and it makes stale-vs-fabricated unscoreable.
    if item.get("prior_year_answer") and item.get("prior_year_answer") == item.get("gold_answer"):
        errors.append(f"{where}: prior_year_answer equals gold_answer — this item does not test volatility")

    # The whole point of splitting a fee into amount and period (DD-008) is that both are
    # quoted. If either drifts out of the quote the guarantee stated in the paper — every
    # part of the answer appears inside the quote a person accepted — is no longer true,
    # and nothing else in the pipeline would notice.
    parts = item.get("answer_parts")
    if parts:
        quote = normalise(item.get("source_quote", ""))
        for name in ("amount", "qualifier"):
            value = normalise(parts.get(name, ""))
            if not value:
                errors.append(f"{where}: answer_parts.{name} is empty")
            elif value not in quote:
                errors.append(f"{where}: answer_parts.{name} {parts[name]!r} is not in "
                              f"the source quote — DD-008 guarantee broken")
        composed = normalise(item.get("gold_answer", ""))
        for name in ("amount", "qualifier"):
            if normalise(parts.get(name, "")) not in composed:
                errors.append(f"{where}: gold_answer {item.get('gold_answer')!r} does not "
                              f"contain its own {name}")

    # A gold answer is compared to model output by the scorer, and the scorer's fallback
    # for long text is a substring test. A verbose gold answer therefore penalises being
    # right: "TOEFL iBT total score 4.5 and 4.0 in all subtests: reading, listening,
    # writing, and speaking" was accepted into the dataset, and a model answering
    # "TOEFL iBT 4.5" — correct — would never contain that string. The gold answer is a
    # value, not a sentence; the sentence's place is source_quote.
    if parts:
        amount = parts.get("amount", "")
        numbers = re.findall(r"\d[\d,]*(?:\.\d+)?", amount)   # "33,360" is one number
        if len(numbers) > 1:
            errors.append(f"{where}: answer_parts.amount {amount[:50]!r} carries "
                          f"{len(numbers)} numbers — one value per item; sub-scores and "
                          f"floors belong in the quote, not the answer")
        elif len(amount) > 40:
            errors.append(f"{where}: answer_parts.amount is {len(amount)} chars — "
                          f"a value, not a sentence; the sentence belongs in source_quote")

    # A range accepts either of its ends: the scorer extracts every number, so a gold
    # answer of "3-4 semesters" scores "3 semesters" correct. If the page states a range,
    # either the fact is not well-defined enough to test, or the page elsewhere states
    # the norm ("Normally ... 4 semesters") and that is the answer.
    for text in (item.get("gold_answer", ""), *item.get("acceptable_variants", [])):
        # Dates ("2026-2027", "30 June") and cycle labels legitimately contain hyphenated
        # numbers; the hazard is ranges in countable answers.
        if item.get("fact_type") in ("deadline",):
            continue
        if re.search(r"\d\s*[-–—]\s*\d", text) and not re.search(r"20\d{2}", text):
            errors.append(f"{where}: {text[:40]!r} contains a numeric range — the scorer "
                          f"would credit either end of it")

    # A cycle-stamped item asks about the intake read off its page; if the question does
    # not name it, the item silently reverts to asking about a default year.
    if item.get("cycle_quoted"):
        years = re.findall(r"20\d{2}", item["cycle_quoted"])
        if years and not any(y in item.get("question_en", "") for y in years):
            errors.append(f"{where}: intake {item['cycle_quoted']!r} was read off the page "
                          f"but question_en names no year from it")

    return errors


def check_duplicates(items):
    """Two kinds of duplicate: a repeated id, and the same question asked twice.

    Returns (errors, warnings)."""
    errors, warnings = [], []

    ids = Counter(item.get("id") for _, item in items)
    for item_id, count in ids.items():
        if count > 1:
            errors.append(f"duplicate id {item_id!r} appears {count} times")

    # The same fact about the same university asked twice inflates whichever cell it
    # lands in and makes the items non-independent. Keyed on the question, not on
    # (university, fact_type, answer): TUM legitimately requires IELTS 6.5 for both the
    # BSc and the MSc — same answer, two different questions, two valid items. What is
    # never valid is one question with two rows, and the question check below owns that.
    # The value-level collision is still worth a warning, because two items whose gold
    # answers coincide are correlated evidence even when the questions differ.
    facts = Counter(
        (item.get("university"), item.get("fact_type"), item.get("gold_answer"))
        for _, item in items
    )
    for (university, fact_type, answer), count in facts.items():
        if count > 1:
            warnings.append(
                f"{university} / {fact_type} / {answer!r} appears {count} times "
                f"(different levels?) — the items are correlated, not independent"
            )

    questions = Counter(item.get("question_en", "").strip().lower() for _, item in items)
    for question, count in questions.items():
        if count > 1 and question:
            errors.append(f"duplicate question_en ({count}x): {question[:70]}...")

    return errors, warnings


def report_balance(items):
    """Print the cell counts and warn where the design is at risk.

    This is the part that decides whether the study can answer its main question. The
    interaction test needs every coverage_tier to contain both volatile and stable
    facts in comparable numbers; if it does not, the coverage and volatility effects
    are confounded and no amount of analysis fixes it afterwards.
    """
    warnings = []
    records = [item for _, item in items]

    print("\ncoverage_tier x volatility  (the cells the interaction test runs on)")
    print(f"{'':8} {'annual':>8} {'stable':>8} {'total':>8}")
    for tier in ("high", "mid", "low"):
        annual = sum(1 for i in records if i.get("coverage_tier") == tier and i.get("volatility") == "annual")
        stable = sum(1 for i in records if i.get("coverage_tier") == tier and i.get("volatility") == "stable")
        print(f"{tier:8} {annual:8} {stable:8} {annual + stable:8}")
        for label, count in (("annual", annual), ("stable", stable)):
            if count == 0:
                warnings.append(
                    f"cell {tier}/{label} is EMPTY — the interaction test cannot run, "
                    f"and the coverage and volatility effects are confounded"
                )
            elif count < MIN_ITEMS_PER_CELL:
                warnings.append(
                    f"cell {tier}/{label} has {count} items (target {MIN_ITEMS_PER_CELL}+)"
                )

    print("\nfact_type x coverage_tier  (watch for a fact type that lives in only one tier)")
    fact_types = sorted(ALLOWED_VALUES["fact_type"])
    print(f"{'':20} {'high':>6} {'mid':>6} {'low':>6}")
    for fact_type in fact_types:
        counts = [
            sum(1 for i in records if i.get("fact_type") == fact_type and i.get("coverage_tier") == tier)
            for tier in ("high", "mid", "low")
        ]
        print(f"{fact_type:20} {counts[0]:6} {counts[1]:6} {counts[2]:6}")
        if sum(counts) > 0 and sum(1 for c in counts if c > 0) == 1:
            only = ("high", "mid", "low")[[c > 0 for c in counts].index(True)]
            warnings.append(
                f"fact_type '{fact_type}' appears only in tier '{only}' — "
                f"its fact type and its tier cannot be told apart in the results"
            )

    print("\nitems per university")
    per_university = Counter(i.get("university") for i in records)
    for university, count in sorted(per_university.items(), key=lambda kv: -kv[1]):
        print(f"  {university:32} {count:4}")
    if per_university:
        most_common, highest = per_university.most_common(1)[0]
        if highest > len(records) * 0.25:
            warnings.append(
                f"'{most_common}' accounts for {highest}/{len(records)} items — "
                f"one institution's quirks will drive the tier-level result"
            )

    # Round 2 is the whole quality argument of the dataset. Track the progress.
    round2 = sum(1 for i in records if i.get("verification_round") == 2)
    print(f"\nsecond-pass verified: {round2}/{len(records)}")
    if round2 < len(records):
        warnings.append(f"{len(records) - round2} items have not had a second verification pass")

    # Inter-pass disagreement: the honesty number that goes in the paper.
    disagreements = sum(1 for i in records if i.get("round1_gold_answer"))
    if round2:
        rate = disagreements / round2 * 100
        print(f"inter-pass disagreements: {disagreements}/{round2} ({rate:.1f}%)  <- report this in the paper")

    return warnings


def main():
    path = Path(sys.argv[1] if len(sys.argv) > 1 else "data/benchmark.jsonl")
    if not path.exists():
        print(f"error: {path} does not exist")
        return 1

    items, errors = load_items(path)
    print(f"loaded {len(items)} items from {path}")
    if not items:
        print("error: file is empty")
        return 1

    for line_number, item in items:
        errors.extend(check_fields(line_number, item))
    duplicate_errors, duplicate_warnings = check_duplicates(items)
    errors.extend(duplicate_errors)
    warnings = duplicate_warnings + report_balance(items)

    if errors:
        print(f"\n{len(errors)} ERROR(S) — these block the dataset:")
        for error in errors:
            print(f"  x {error}")
    if warnings:
        print(f"\n{len(warnings)} WARNING(S) — these do not block, but read them:")
        for warning in warnings:
            print(f"  ! {warning}")
    if not errors and not warnings:
        print("\nclean.")

    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
