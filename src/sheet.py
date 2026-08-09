"""Annotate in a spreadsheet instead of the terminal.

    python3 src/sheet.py make            # create data/annotation_sheet.csv
    python3 src/sheet.py make --level ug # the undergraduate half
    python3 src/sheet.py import          # read the filled sheet into the benchmark

Typing long quotes into a terminal prompt is slow and error-prone. This produces a CSV
with every mechanical column already filled — id, institution, tier, fact type,
volatility, both question wordings — and four empty columns for the things a person
reads off an official page.

Open it in Numbers or Excel, fill the empty columns, save it back as CSV, then run
`import`. Rows left blank are skipped, so the sheet can be filled over many sittings.

The four columns you fill:

    page_url            the official page the fact is stated on
    gold_answer         the answer exactly as that page words it
    source_quote        the sentence that states it, copied verbatim
    prior_year_answer   the same fact for the previous cycle (annual facts only)

Two optional columns: `acceptable_variants` (other wordings, separated by |) and
`notes` (contradictions, ambiguity — these end up in the paper).
"""

import argparse
import csv
import json
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from new_item import FACTS, LEVELS, UNIVERSITIES, render_questions  # noqa: E402 — same directory, shared definitions

SHEET = Path("data/annotation_sheet.csv")
BENCHMARK = Path("data/benchmark.jsonl")

COLUMNS = [
    "id", "university", "tier", "fact", "volatility", "where_to_look",
    "page_url", "gold_answer", "source_quote", "prior_year_answer",
    "acceptable_variants", "notes",
    "question_en", "question_ru", "snapshot_name",
]

# Pages verified with an HTTP request on 2026-08-07/08. `None` means not found yet — the
# sheet then offers a site-scoped search link instead, which keeps working even when a
# university restructures its site. MBZUAI's own admissions URL 404'd during this
# project, so hard-coded links are treated as hints, never as guarantees.
SOURCES = {
    "mbzuai":     {"domain": "mbzuai.ac.ae",
                   "admissions_pg": "https://mbzuai.ac.ae/study/graduate-admission-process/",
                   "admissions_ug": "https://mbzuai.ac.ae/study/undergraduate-admission-process/",
                   "program_ug": "https://mbzuai.ac.ae/study/undergraduate-program/",
                   "about": "https://mbzuai.ac.ae/about/fast-facts/"},
    "mit":        {"domain": "mit.edu",
                   "admissions_pg": "https://gradadmissions.mit.edu/programs/deadlines",
                   "english_pg": "https://oge.mit.edu/graduate-admissions/applications/standardized-tests/toefl-ibt/",
                   "fees_pg": "https://registrar.mit.edu/registration-academics/tuition-fees/graduate",
                   "program_pg": "https://gradadmissions.mit.edu/programs/",
                   "about": "https://www.mit.edu/about/"},
    "delft":      {"domain": "tudelft.nl",
                   "admissions_pg": "https://www.tudelft.nl/en/education/programmes/masters/cs/msc-computer-science/admission-and-application",
                   "program_pg": "https://www.tudelft.nl/en/education/programmes/masters/cs/msc-computer-science",
                   "about": "https://www.tudelft.nl/en/about-tu-delft"},
    "trinity":    {"domain": "tcd.ie",
                   "admissions_pg": "https://www.tcd.ie/scss/courses/postgraduate/computer-science/application-requirements/",
                   "program_pg": "https://www.tcd.ie/scss/courses/postgraduate/computer-science/",
                   "about": "https://www.tcd.ie/about/",
                   "english_pg": "https://www.tcd.ie/study/international/english-language-requirements/",
                   "english_ug": "https://www.tcd.ie/study/international/english-language-requirements/"},
    "kaist":      {"domain": "kaist.ac.kr",
                   "admissions_pg": "https://admission.kaist.ac.kr/intl-graduate/Admission/YearlyTimelines",
                   "admissions_ug": "https://admission.kaist.ac.kr/intl-undergraduate/",
                   "about": "https://www.kaist.ac.kr/en/"},
    "indonesia":  {"domain": "ui.ac.id",
                   "admissions_pg": "https://penerimaan.ui.ac.id/en/",
                   "admissions_ug": "https://penerimaan.ui.ac.id/en/",
                   "program_pg": "https://cs.ui.ac.id/en/magister-ilmu-komputer/"},
    "harvard":    {"domain": "harvard.edu",
                   "admissions_pg": "https://gsas.harvard.edu/apply/applying-degree-programs",
                   "admissions_ug": "https://college.harvard.edu/admissions",
                   "fees_pg": "https://gsas.harvard.edu/apply/cost-attendance-2026-2027",
                   "program_ug": "https://college.harvard.edu/academics/liberal-arts-sciences",
                   "about": "https://www.harvard.edu/about/"},
    "stanford":   {"domain": "stanford.edu",
                   "admissions_pg": "https://gradadmissions.stanford.edu/apply/dates-and-deadlines",
                   "admissions_ug": "https://www.stanford.edu/admission/",
                   "fees_pg": "https://studentservices.stanford.edu/tuition-rates",
                   "about": "https://www.stanford.edu/about/",
                   "program_pg": "https://www.cs.stanford.edu/masters-program-overview",
                   "english_pg": "https://www.cs.stanford.edu/admissions/masters-admissions"},
    "cambridge":  {"domain": "cam.ac.uk",
                   "admissions_pg": "https://www.postgraduate.study.cam.ac.uk/courses/directory/cscsmpacs/requirements",
                   "admissions_ug": "https://www.undergraduate.study.cam.ac.uk/applying",
                   "program_pg": "https://www.cst.cam.ac.uk/admissions/acs",
                   "about": "https://www.cam.ac.uk/about-us",
                   "english_pg": "https://www.postgraduate.study.cam.ac.uk/apply/before/english-language-requirements"},
    "bologna":    {"domain": "unibo.it",
                   "admissions_pg": "https://corsi.unibo.it/2cycle/artificial-intelligence/admission",
                   "program_pg": "https://corsi.unibo.it/2cycle/artificial-intelligence",
                   "about": "https://www.unibo.it/en/university"},
    "nazarbayev": {"domain": "nu.edu.kz",
                   "admissions_pg": "https://nu.edu.kz/sprogram/master-of-science-in-computer-science/",
                   "admissions_ug": "https://nu.edu.kz/admissions/",
                   "program_pg": "https://seds.nu.edu.kz/msc_in_cs",
                   "about": "https://nu.edu.kz/academics/"},
    "innopolis":  {"domain": "innopolis.university",
                   "admissions_pg": "https://apply.innopolis.university/en/",
                   "admissions_ug": "https://apply.innopolis.university/en/",
                   "about": "https://innopolis.university/en/about/"},
    # Added 2026-08-08 when the institution list grew to 25. Admissions URLs verified
    # with an HTTP request that day; programme and fee pages still to be found, and the
    # sheet falls back to a site-scoped search for those.
    "eth":        {"domain": "ethz.ch",
                   "admissions_pg": "https://ethz.ch/en/studies/master/application.html",
                   "admissions_ug": "https://ethz.ch/en/studies/bachelor.html",
                   "about": "https://ethz.ch/en/the-eth-zurich.html",
                   "program_pg": "https://ethz.ch/en/studies/master/degree-programmes/engineering-sciences/computer-science.html",
                   "english_pg": "https://ethz.ch/en/studies/master/application/language-requirements.html"},
    "imperial":   {"domain": "imperial.ac.uk",
                   "admissions_pg": "https://www.imperial.ac.uk/study/apply/postgraduate-taught/entry-requirements/",
                   "program_pg": "https://www.imperial.ac.uk/study/courses/postgraduate-taught/computing/",
                   "about": "https://www.imperial.ac.uk/about/"},
    "yale":       {"domain": "yale.edu",
                   "admissions_pg": "https://gsas.yale.edu/admissions/phdmasters-application-process/dates-deadlines",
                   "program_pg": "https://engineering.yale.edu/academic-study/departments/computer-science/graduate-study/master-science-program"},
    "nus":        {"domain": "nus.edu.sg",
                   "admissions_pg": "https://www.comp.nus.edu.sg/programmes/pg/mcs/admissions/",
                   "program_pg": "https://www.comp.nus.edu.sg/programmes/pg/mcs/",
                   "fees_pg": "https://www.comp.nus.edu.sg/programmes/pg/misc/scholarships/"},
    "kth":        {"domain": "kth.se",
                   "admissions_pg": "https://www.kth.se/en/studies/master/admissions",
                   "fees_pg": "https://www.kth.se/en/studies/master/computer-science/fees-communication-systems-1.909945"},
    "aalto":      {"domain": "aalto.fi",
                   "admissions_pg": "https://www.aalto.fi/en/study-at-aalto/apply-to-masters-programmes",
                   "program_pg": "https://www.aalto.fi/en/study-options/computer-science-master-of-science-technology",
                   "fees_pg": "https://www.aalto.fi/en/admission-services/scholarships-and-tuition-fees"},
    "tum":        {"domain": "tum.de",
                   "admissions_pg": "https://www.tum.de/en/studies/application",
                   "program_pg": "https://www.tum.de/en/studies/degree-programs/detail/informatics-master-of-science-msc",
                   "fees_pg": "https://www.tum.de/en/studies/fees/tuition"},
    "warsaw":     {"domain": "uw.edu.pl",
                   "admissions_pg": "https://en.uw.edu.pl/admissions-for-the-2026-2027-academic-year/",
                   "admissions_ug": "https://en.uw.edu.pl/admissions-for-the-2026-2027-academic-year/"},
    "malaya":     {"domain": "um.edu.my",
                   "admissions_pg": "https://study.um.edu.my/"},
    "chula":      {"domain": "chula.ac.th",
                   "admissions_pg": "https://www.chula.ac.th/en/admissions/",
                   "program_pg": "https://www.cp.eng.chula.ac.th/en/prospective/graduate/master-computerscience/",
                   "fees_pg": "https://www.chula.ac.th/en/academics/admissions/tuition-and-fees/"},
    "urfu":       {"domain": "urfu.ru",
                   "admissions_pg": "https://urfu.ru/en/admission/"},
    "vnu":        {"domain": "vnu.edu.vn",
                   "admissions_pg": "https://vnu.edu.vn/eng/"},
    "auca":       {"domain": "auca.kg",
                   "admissions_pg": "https://auca.kg/en/"},
}

# Which kind of page each fact usually lives on.
FACT_PAGE = {
    "deadline": "admissions", "tuition": "admissions", "english": "admissions",
    "documents": "admissions", "eligibility": "admissions",
    "language": "program", "duration": "program", "city": "about",
}

# Search terms used when no verified link exists for that university.
FACT_TERMS = {
    "deadline": "application deadline",
    "tuition": "tuition fees per year",
    "english": "TOEFL minimum score requirement",
    "documents": "letters of recommendation referees required",
    "eligibility": "entry requirements degree GPA",
    "language": "language of instruction",
    "duration": "programme duration years",
    "city": "campus location city",
}

LEVEL_TERMS = {"pg": "graduate master", "ug": "undergraduate bachelor"}


def where_to_look(key, fact, level):
    """Best available starting point for this row: a verified page, or a search."""
    source = SOURCES.get(key, {})
    page = FACT_PAGE[fact]
    known = source.get(f"{page}_{level}") or source.get(page)
    if known:
        return known

    from urllib.parse import quote_plus
    query = f"site:{source.get('domain', '')} {LEVEL_TERMS[level]} {FACT_TERMS[fact]}"
    return f"https://www.google.com/search?q={quote_plus(query)}"


def build_rows(level):
    """One row per institution x fact, with everything a computer can know filled in."""
    level_en, level_ru_acc, level_ru_prep = LEVELS[level]
    rows = []
    for key, (name, country, tier) in UNIVERSITIES.items():
        for fact, (fact_type, volatility, q_en, q_ru) in FACTS.items():
            q_en_text, q_ru_text = render_questions(key, level, fact)
            rows.append({
                "id": f"{key}-{level}-{fact}",
                "university": name,
                "tier": tier,
                "fact": fact,
                "volatility": volatility,
                "where_to_look": where_to_look(key, fact, level),
                "page_url": "",
                "gold_answer": "",
                "source_quote": "",
                # Marked not-applicable rather than left blank, so it is obvious at a
                # glance that a stable fact is not missing data.
                "prior_year_answer": "" if volatility == "annual" else "n/a",
                "acceptable_variants": "",
                "notes": "",
                "question_en": q_en_text,
                "question_ru": q_ru_text,
                "snapshot_name": f"{key}-{level}-{fact}",
            })
    return rows


def make(level, force):
    if SHEET.exists() and not force:
        print(f"{SHEET} already exists. Filled rows would be lost.")
        print("  To add the other level:   python3 src/sheet.py make --level ug --append")
        print("  To start over:            python3 src/sheet.py make --force")
        return 1

    rows = build_rows(level)
    SHEET.parent.mkdir(parents=True, exist_ok=True)
    with SHEET.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=COLUMNS)
        writer.writeheader()
        writer.writerows(rows)

    print(f"Created {SHEET} with {len(rows)} rows ({len(UNIVERSITIES)} institutions x {len(FACTS)} facts).")
    print("\nOpen it:   open -a Numbers data/annotation_sheet.csv")
    print("Fill:      page_url, gold_answer, source_quote, prior_year_answer")
    print("Save as CSV (Numbers: File > Export To > CSV, replacing the same file).")
    print("Then:      python3 src/sheet.py import")
    return 0


def append(level):
    """Add another level's rows to an existing sheet without touching filled ones."""
    if not SHEET.exists():
        return make(level, force=False)
    existing = list(read_sheet())
    have = {r["id"] for r in existing}
    new = [r for r in build_rows(level) if r["id"] not in have]
    if not new:
        print("Nothing to add — those rows are already in the sheet.")
        return 0
    with SHEET.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=COLUMNS)
        writer.writeheader()
        writer.writerows(existing + new)
    print(f"Added {len(new)} row(s). {SHEET} now has {len(existing) + len(new)}.")
    return 0


def found_snapshot(name):
    """Locate the archived page for this item.

    Returns (path, access_date). If several archives exist for the same item — which
    happens when a page is re-archived weeks later for the drift measurement — the most
    recent one wins, and its date becomes date_accessed. If none exists yet, fall back
    to today's date so the row still imports; validate.py will then flag the missing
    file, which is the right place for that complaint.
    """
    matches = sorted(Path("data/snapshots").glob(f"{name}-*.html"))
    if not matches:
        return Path(f"data/snapshots/{name}-{date.today().isoformat()}.html"), date.today().isoformat()
    newest = matches[-1]
    return newest, newest.stem[len(name) + 1:]


def read_sheet():
    with SHEET.open(encoding="utf-8-sig", newline="") as f:
        for row in csv.DictReader(f):
            yield {c: (row.get(c) or "").strip() for c in COLUMNS}


def import_sheet():
    if not SHEET.exists():
        print(f"{SHEET} not found. Create it with: python3 src/sheet.py make")
        return 1

    already = set()
    if BENCHMARK.exists():
        for line in BENCHMARK.read_text(encoding="utf-8").splitlines():
            if line.strip():
                already.add(json.loads(line)["id"])

    added, skipped_blank, skipped_dup, problems = 0, 0, 0, []

    with BENCHMARK.open("a", encoding="utf-8") as out:
        for row in read_sheet():
            # A row counts as filled only when all three required fields are present.
            # A half-filled row is a mistake, not a partial item, so it is reported.
            filled = [bool(row["page_url"]), bool(row["gold_answer"]), bool(row["source_quote"])]
            if not any(filled):
                skipped_blank += 1
                continue
            if not all(filled):
                missing = [n for n, ok in zip(("page_url", "gold_answer", "source_quote"), filled) if not ok]
                problems.append(f"{row['id']}: partially filled, missing {', '.join(missing)}")
                continue
            if row["id"] in already:
                skipped_dup += 1
                continue
            if not row["page_url"].startswith("https://"):
                problems.append(f"{row['id']}: page_url must start with https://")
                continue

            key, level, fact = row["id"].split("-", 2)
            name, country, tier = UNIVERSITIES[key]
            fact_type, volatility, _, _ = FACTS[fact]

            prior = row["prior_year_answer"]
            if volatility == "stable" or prior.lower() in ("n/a", "na", "-"):
                prior = None
            if prior and prior == row["gold_answer"]:
                problems.append(f"{row['id']}: prior_year_answer equals gold_answer — "
                                f"the fact did not change, so it does not test volatility")
                prior = None

            out.write(json.dumps({
                "id": row["id"],
                "university": name,
                "country": country,
                "coverage_tier": tier,
                "question_en": row["question_en"],
                "question_ru": row["question_ru"],
                "fact_type": fact_type,
                "volatility": volatility,
                "gold_answer": row["gold_answer"],
                "acceptable_variants": [v.strip() for v in row["acceptable_variants"].split("|") if v.strip()],
                "prior_year_answer": prior,
                "source_url": row["page_url"],
                "source_quote": row["source_quote"],
                # Point at the snapshot that actually exists rather than assuming it was
                # archived today: a sitting that spans midnight, or archiving one evening
                # and importing the next morning, would otherwise write a path to a file
                # that is not there. date_accessed follows the snapshot for the same
                # reason — it records when the page was read, not when it was imported.
                "snapshot_path": str(found_snapshot(row["snapshot_name"])[0]),
                "date_accessed": found_snapshot(row["snapshot_name"])[1],
                "verified_by": "author",
                "verification_round": 1,
                "round1_gold_answer": None,
                "notes": row["notes"],
            }, ensure_ascii=False) + "\n")
            added += 1

    print(f"Imported {added} item(s) into {BENCHMARK}.")
    if skipped_dup:
        print(f"  {skipped_dup} already there, left alone.")
    if skipped_blank:
        print(f"  {skipped_blank} row(s) still empty.")
    if problems:
        print(f"\n  {len(problems)} row(s) need attention:")
        for problem in problems:
            print(f"    ! {problem}")

    print("\nNext:")
    print("  python3 src/validate.py     check the data")
    print("  python3 src/progress.py     see what is left")
    print("\nSnapshots are still required — validate.py will name any that are missing:")
    print("  python3 src/collect.py <url> <snapshot_name from the sheet>")
    return 0


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("command", choices=["make", "import"])
    parser.add_argument("--level", default="pg", choices=sorted(LEVELS))
    parser.add_argument("--force", action="store_true", help="overwrite an existing sheet")
    parser.add_argument("--append", action="store_true", help="add this level's rows to the sheet")
    args = parser.parse_args()

    if args.command == "make":
        return append(args.level) if args.append else make(args.level, args.force)
    return import_sheet()


if __name__ == "__main__":
    sys.exit(main())
