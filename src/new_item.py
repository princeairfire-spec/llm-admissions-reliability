"""Print a benchmark item skeleton with the mechanical fields already filled.

    python3 src/new_item.py mbzuai deadline
    python3 src/new_item.py mbzuai tuition --level ug --cycle "Fall 2027"
    python3 src/new_item.py oxford language

Everything a computer can know — id, institution, country, coverage tier, fact type,
volatility, today's date, and both question wordings — is generated. Four fields are
left blank on purpose:

    gold_answer         what the official page says
    prior_year_answer   what it said for the previous cycle (annual facts only)
    source_quote        the exact sentence that establishes the answer
    source_url          the page it came from

Those four are read off an official page by a person. Not because of a rule, but
because the whole study is a comparison between what a model says and what a human
verified. If a model supplied the gold answers, a shared misreading would be invisible:
wrong in the answer, wrong in the standard, and scored correct.

Append the output to data/benchmark.jsonl, fill the blanks, then run src/validate.py.
"""

import argparse
import json
import sys
from datetime import date
from pathlib import Path

# From docs/universities.md. Tier is a property of the institution, assigned once, so
# it cannot drift between items and blur the coverage axis.
UNIVERSITIES = {
    # high — top-of-mind globally, heavy English-language web presence
    "harvard":   ("Harvard University",       "US", "high"),
    "mit":       ("MIT",                      "US", "high"),
    # Oxford was replaced by Cambridge on 2026-08-08: every ox.ac.uk page answers 403 to
    # a non-browser request, so its pages cannot be archived. Berkeley, Princeton and
    # Auckland were dropped for the same reason. See docs/universities.md — this is a
    # selection effect that falls mostly on the high tier and belongs in Limitations.
    "cambridge": ("University of Cambridge",  "GB", "high"),
    "stanford":  ("Stanford University",      "US", "high"),
    "eth":       ("ETH Zurich",               "CH", "high"),
    "imperial":  ("Imperial College London",  "GB", "high"),
    "yale":      ("Yale University",          "US", "high"),
    "nus":       ("National University of Singapore", "SG", "high"),

    # mid — strong and well known regionally, outside the global top ten
    "delft":     ("TU Delft",                 "NL", "mid"),
    "trinity":   ("Trinity College Dublin",   "IE", "mid"),
    "kaist":     ("KAIST",                    "KR", "mid"),
    "bologna":   ("University of Bologna",    "IT", "mid"),
    "kth":       ("KTH Royal Institute of Technology", "SE", "mid"),
    "aalto":     ("Aalto University",         "FI", "mid"),
    "tum":       ("Technical University of Munich", "DE", "mid"),
    "warsaw":    ("University of Warsaw",     "PL", "mid"),
    "malaya":    ("Universiti Malaya",        "MY", "mid"),

    # low — limited presence in the English-language web
    "mbzuai":    ("MBZUAI",                   "AE", "low"),
    "nazarbayev":("Nazarbayev University",    "KZ", "low"),
    "innopolis": ("Innopolis University",     "RU", "low"),
    "indonesia": ("Universitas Indonesia",    "ID", "low"),
    "chula":     ("Chulalongkorn University", "TH", "low"),
    "urfu":      ("Ural Federal University",  "RU", "low"),
    "vnu":       ("Vietnam National University", "VN", "low"),
    "auca":      ("American University of Central Asia", "KG", "low"),
}

# One named degree programme per institution and level.
#
# Facts were originally asked at institution level — "the annual tuition fee for
# Harvard's graduate programs". Testing showed that question has no answer: Harvard
# publishes tiered tuition by year of study and separate figures per programme, so every
# extracted candidate was correctly rejected as answering a different question. The same
# applies to deadlines (Early Action vs Regular Decision) and English requirements
# (departments set their own minimums).
#
# Scoping to a named programme makes each fact single-valued, and it also matches what
# an applicant actually asks: nobody asks what Harvard costs, they ask what their
# programme costs.
PROGRAMS = {
    "harvard":    {"pg": "the Master of Science in Computational Science and Engineering",
                   "ug": "the undergraduate program"},
    "mit":        {"pg": "the master's program in Electrical Engineering and Computer Science",
                   "ug": "the undergraduate program"},
    "cambridge":  {"pg": "the MPhil in Advanced Computer Science",
                   "ug": "the BA in Computer Science"},
    "stanford":   {"pg": "the MS in Computer Science", "ug": "the undergraduate program"},
    "delft":      {"pg": "the MSc in Computer Science", "ug": "the BSc in Computer Science and Engineering"},
    "trinity":    {"pg": "the MSc in Computer Science", "ug": "the BA in Computer Science"},
    "kaist":      {"pg": "the master's program in Computer Science", "ug": "the undergraduate program"},
    "bologna":    {"pg": "the second cycle degree in Artificial Intelligence",
                   "ug": "the first cycle degree in Computer Science"},
    "mbzuai":     {"pg": "the MSc in Computer Science", "ug": "the BSc in Artificial Intelligence"},
    "nazarbayev": {"pg": "the MSc in Computer Science", "ug": "the BSc in Computer Science"},
    "innopolis":  {"pg": "the MSc in Computer Science", "ug": "the BSc in Computer Science"},
    "indonesia":  {"pg": "the master's program in Computer Science", "ug": "the undergraduate program"},
    "eth":        {"pg": "the MSc in Computer Science", "ug": "the BSc in Computer Science"},
    "imperial":   {"pg": "the MSc in Computing", "ug": "the BEng in Computing"},
    "yale":       {"pg": "the MS in Computer Science", "ug": "the BS in Computer Science"},
    "nus":        {"pg": "the MComp in Computer Science", "ug": "the BComp in Computer Science"},
    "kth":        {"pg": "the MSc in Computer Science", "ug": "the BSc in Information and Communication Technology"},
    "aalto":      {"pg": "the MSc in Computer Science", "ug": "the BSc in Science and Technology"},
    "tum":        {"pg": "the MSc in Informatics", "ug": "the BSc in Informatics"},
    "warsaw":     {"pg": "the MSc in Computer Science", "ug": "the BSc in Computer Science"},
    "malaya":     {"pg": "the MSc in Computer Science", "ug": "the BSc in Computer Science"},
    "chula":      {"pg": "the MSc in Computer Science", "ug": "the BSc in Computer Engineering"},
    "urfu":       {"pg": "the MSc in Computer Science", "ug": "the BSc in Computer Science"},
    "vnu":        {"pg": "the MSc in Information Technology", "ug": "the BSc in Information Technology"},
    "auca":       {"pg": "the MSc in Computer Science", "ug": "the BA in Software Engineering"},
}

# Russian needs the study level in two grammatical cases: accusative for "applying to"
# and prepositional for "studying at". Using one form everywhere produces sentences a
# native speaker would not write, and clumsy phrasing in one language would show up in
# the results as a language effect that is really a translation artefact.
LEVELS = {
    "ug": ("undergraduate", "бакалавриат",  "бакалавриате"),
    "pg": ("graduate",      "магистратуру", "магистратуре"),
}

# Each fact type carries its own volatility and its own question wording. The two
# languages are translations of one question, never two different questions — any
# difference in what is asked would confound the language axis with the question.
#
# Wordings name the institution, the level and the cycle explicitly. A question that
# relies on context ("what is the deadline?") is unanswerable in isolation and will be
# scored as a model failure when it is really a question-design failure.
FACTS = {
    "deadline": (
        "deadline", "annual",
        "What is the final application deadline for {prog} at {uni} for {cycle} entry?",
        "Какой финальный дедлайн подачи документов на {prog_ru} в {uni} для поступления {cycle_ru}?",
    ),
    # Both of these used to name the unit the answer had to come in — "annual" fee, a
    # "TOEFL iBT" score. Universities do not agree on either: MIT publishes tuition per
    # term, KTH for the full programme, and plenty of places list IELTS and no TOEFL. A
    # question phrased around one convention has no answer on the official pages of the
    # universities that use another, and since convention travels with country and tier,
    # dropping them would have turned the tier comparison into a comparison of publishing
    # habits. So the question asks for the unit instead of assuming it, and the unit is
    # quoted from the page like everything else.
    "tuition": (
        "tuition", "annual",
        "What is the tuition fee for {prog} at {uni} for {cycle} entry? "
        "State the amount and the period it covers, as the university states them.",
        "Какова стоимость обучения на {prog_ru} в {uni} для поступления {cycle_ru}? "
        "Укажите сумму и период, за который она взимается, как их указывает университет.",
    ),
    "english": (
        "test_requirement", "annual",
        "What is the minimum English language test score required for admission to "
        "{prog} at {uni} for {cycle} entry? Name the test and the score.",
        "Какой минимальный балл языкового теста нужен для поступления на {prog_ru} "
        "в {uni} {cycle_ru}? Назовите тест и балл.",
    ),
    "documents": (
        "document_list", "annual",
        "How many letters of recommendation are required to apply to {prog} at {uni} for {cycle} entry?",
        "Сколько рекомендательных писем требуется для поступления на {prog_ru} в {uni} {cycle_ru}?",
    ),
    "language": (
        "program_structure", "stable",
        "What is the language of instruction for {prog} at {uni}?",
        "На каком языке ведётся обучение на {prog_ru} в {uni}?",
    ),
    "duration": (
        "program_structure", "stable",
        "What is the standard duration of {prog} at {uni}?",
        "Какова стандартная длительность обучения на {prog_ru} в {uni}?",
    ),
    "city": (
        "program_structure", "stable",
        "In which city is {uni}'s main campus located?",
        "В каком городе находится основной кампус {uni}?",
    ),
    "eligibility": (
        "eligibility", "stable",
        "What is the minimum academic requirement to apply to {prog} at {uni}?",
        "Какое минимальное академическое требование предъявляется для поступления на {prog_ru} в {uni}?",
    ),
}


def question_fields(university, level, cycle="Fall 2027", cycle_ru="осенью 2027 года"):
    """Everything the question templates interpolate. One place, so the three callers
    (new_item, sheet, verify) cannot drift apart and ask subtly different questions."""
    name = UNIVERSITIES[university][0]
    level_en, level_ru_acc, level_ru_prep = LEVELS[level]
    prog = PROGRAMS[university][level]
    # Russian keeps the programme's English name — that is how a Russian speaker refers
    # to a foreign degree — but the English article has to go: "на the MSc" is not
    # Russian, "на MSc in Computer Science" is.
    prog_ru = prog[4:] if prog.startswith("the ") else prog
    # Named degrees keep their English title — that is how a Russian speaker refers to a
    # foreign programme. But the generic placeholder has no English title to keep, and
    # "на undergraduate program" is not Russian; use the ordinary Russian word instead.
    if prog_ru in ("undergraduate program", "graduate program"):
        prog_ru = level_ru_acc
    # The same repair for the half-generic pattern: "на master's program in X" is not
    # Russian either. The named part keeps its English, the generic part translates.
    elif prog_ru.startswith("master's program in "):
        prog_ru = "магистерскую программу по " + prog_ru[len("master's program in "):]
    elif prog_ru.startswith("bachelor's program in "):
        prog_ru = "бакалаврскую программу по " + prog_ru[len("bachelor's program in "):]
    return {"uni": name, "level_en": level_en,
            "level_ru_acc": level_ru_acc, "level_ru_prep": level_ru_prep,
            "prog": prog, "prog_ru": prog_ru,
            "cycle": cycle, "cycle_ru": cycle_ru}


def render_questions(university, level, fact, cycle="Fall 2027", cycle_ru="осенью 2027 года"):
    """The English and Russian wording for one item."""
    _, _, q_en, q_ru = FACTS[fact]
    fields = question_fields(university, level, cycle, cycle_ru)
    return q_en.format(**fields), q_ru.format(**fields)


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("university", choices=sorted(UNIVERSITIES), help="institution key")
    parser.add_argument("fact", nargs="?", choices=sorted(FACTS),
                        help="which fact to ask about; omit when using --facts")
    parser.add_argument("--facts", metavar="LIST",
                        help="comma-separated fact list, e.g. deadline,tuition,language,duration. "
                             "Walks through them in one sitting, which is far faster than "
                             "re-running the command per fact while the page is already open.")
    parser.add_argument("--level", default="pg", choices=sorted(LEVELS))
    parser.add_argument("--cycle", default="Fall 2027")
    parser.add_argument("--cycle-ru", default="осенью 2027 года")
    parser.add_argument("--add", action="store_true",
                        help="ask for the four human fields and append to data/benchmark.jsonl")
    args = parser.parse_args()

    if args.facts:
        wanted = [f.strip() for f in args.facts.split(",") if f.strip()]
        unknown = [f for f in wanted if f not in FACTS]
        if unknown:
            parser.error(f"unknown fact(s): {', '.join(unknown)}. Choose from: {', '.join(sorted(FACTS))}")
    elif args.fact:
        wanted = [args.fact]
    else:
        parser.error("give a fact, or use --facts with a comma-separated list")

    if len(wanted) > 1 and not args.add:
        parser.error("--facts is for the interactive flow; add --add")

    results = [build(args, fact) for fact in wanted]

    if not args.add:
        return emit(args, *results[0])

    # One sitting per institution: the page is already open, so the expensive part —
    # finding the right page — is paid once instead of once per fact.
    added, skipped = 0, 0
    for index, (item, volatility) in enumerate(results, start=1):
        if len(results) > 1:
            print(f"\n{'=' * 66}\n  {index}/{len(results)}   {item['id']}\n{'=' * 66}")
        outcome = interactive_add(item, volatility, allow_skip=len(results) > 1)
        if outcome == 0:
            added += 1
        else:
            skipped += 1
    if len(results) > 1:
        print(f"\n  Session finished: {added} added, {skipped} skipped.")
        print("  Check with:  python3 src/validate.py")
    return 0


def build(args, fact):
    """Assemble one item skeleton. Returns (item, volatility)."""
    name, country, tier = UNIVERSITIES[args.university]
    fact_type, volatility, question_en, question_ru = FACTS[fact]
    level_en, level_ru_acc, level_ru_prep = LEVELS[args.level]

    fields = question_fields(args.university, args.level, args.cycle, args.cycle_ru)

    item = {
        "id": f"{args.university}-{args.level}-{fact}",
        "university": name,
        "country": country,
        "coverage_tier": tier,
        "question_en": question_en.format(**fields),
        "question_ru": question_ru.format(**fields),
        "fact_type": fact_type,
        "volatility": volatility,
        "gold_answer": "",
        "acceptable_variants": [],
        # A stable fact had no different earlier value; validate.py rejects one that does.
        "prior_year_answer": "" if volatility == "annual" else None,
        "source_url": "",
        "source_quote": "",
        "snapshot_path": f"data/snapshots/{args.university}-{args.level}-{fact}-{date.today().isoformat()}.html",
        "date_accessed": date.today().isoformat(),
        "verified_by": "author",
        "verification_round": 1,
        "round1_gold_answer": None,
        "notes": "",
    }

    return item, volatility


def emit(args, item, volatility):
    """Non-interactive output: print the skeleton for hand-editing."""
    print(json.dumps(item, ensure_ascii=False))
    blanks = "gold_answer, source_url, source_quote" + (
        ", prior_year_answer" if volatility == "annual" else "")
    print(f"\n# fill in: {blanks}", file=sys.stderr)
    print(f"# archive the page first: python3 src/collect.py <url> "
          f"{Path(item['snapshot_path']).stem.rsplit('-', 3)[0]}", file=sys.stderr)
    return 0


def interactive_add(item, volatility, allow_skip=False):
    """Ask for the four human-supplied fields and append the finished item.

    Hand-editing JSON Lines is where beginners lose items to a stray comma. Prompting
    for exactly the fields a person has to read off the page removes that failure mode
    entirely, and the file stays valid by construction.
    """
    benchmark = Path("data/benchmark.jsonl")
    snapshot = Path(item["snapshot_path"])

    print("\nThis item will ask:")
    print(f"  EN  {item['question_en']}")
    print(f"  RU  {item['question_ru']}")

    if not snapshot.exists():
        print(f"\n  ! No snapshot at {snapshot}")
        print(f"    Archive the page first, in another window:")
        print(f"      python3 src/collect.py <url> {snapshot.stem.rsplit('-', 3)[0]}")
        if input("\n  Continue anyway? [y/N] ").strip().lower() != "y":
            print("  Stopped. Nothing was written.")
            return 1

    # Duplicate ids silently merge items downstream, so refuse before writing.
    if benchmark.exists():
        for line in benchmark.read_text(encoding="utf-8").splitlines():
            if line.strip() and json.loads(line).get("id") == item["id"]:
                print(f"\n  ! {item['id']} is already in {benchmark}. Nothing written.")
                return 1

    hint = "Enter on an empty line skips this fact." if allow_skip else "Enter on an empty line aborts."
    print(f"\nRead these off the official page. {hint}\n")

    item["source_url"] = ask("Page URL (https://...)")
    if not item["source_url"]:
        return abort()
    if not item["source_url"].startswith("https://"):
        print("  ! Must start with https:// — validate.py will reject it otherwise.")
        return abort()

    item["gold_answer"] = ask("The answer, exactly as the page states it")
    if not item["gold_answer"]:
        return abort()

    item["source_quote"] = ask("The sentence from the page that says so (copy it verbatim)")
    if not item["source_quote"]:
        return abort()

    if volatility == "annual":
        print("\n  Previous cycle's value: this is what makes it possible to tell a model")
        print("  that is out of date from one that is inventing. Leave empty if the page")
        print("  does not publish last year's figure.")
        prior = ask("Value for the previous cycle (Enter to skip)", allow_empty=True)
        item["prior_year_answer"] = prior or None
        if prior and prior == item["gold_answer"]:
            print("  ! Same as this year's answer — then the fact did not change, and this")
            print("    item does not test volatility. Recorded as empty instead.")
            item["prior_year_answer"] = None

    variants = ask("Other acceptable wordings, separated by ' | ' (Enter to skip)", allow_empty=True)
    item["acceptable_variants"] = [v.strip() for v in variants.split("|") if v.strip()]

    item["notes"] = ask("Notes — contradictions on the page, ambiguity (Enter to skip)", allow_empty=True)

    benchmark.parent.mkdir(parents=True, exist_ok=True)
    with benchmark.open("a", encoding="utf-8") as out:
        out.write(json.dumps(item, ensure_ascii=False) + "\n")

    total = sum(1 for l in benchmark.read_text(encoding="utf-8").splitlines() if l.strip())
    print(f"\n  Added {item['id']}. {benchmark} now holds {total} item(s).")
    print("  Check it with:  python3 src/validate.py")
    return 0


def ask(prompt, allow_empty=False):
    value = input(f"  {prompt}:\n    ").strip()
    if not value and not allow_empty:
        return ""
    return value


def abort():
    print("\n  Stopped. Nothing was written.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
