"""Propose fact candidates from archived pages, for a human to accept or reject.

    python3 src/extract.py init     # create data/pages.csv — paste URLs into it
    python3 src/extract.py fetch    # archive every page listed there
    python3 src/extract.py run      # propose candidates from the archives

Then review them: python3 src/verify.py

## The line this pipeline does not cross

A model never supplies a gold answer from memory. It is shown an archived page and asked
to copy a fact and the text that states it out of that page. Extraction from a document
in front of the model is a different task from recall, and the output is not trusted on
its own: every candidate passes deterministic checks before a person ever sees it, and a
person then accepts or rejects it against the quote.

    1. The quote must appear verbatim in the archived page.
    2. The extracted value must appear inside the quote.
    3. The quote must carry context beyond the value itself.
    4. Where the value is meaningless alone — a fee without its period, a score without
       its test — that qualifier must also appear inside the quote (DD-008).
    5. Where the fact belongs to an intake — a deadline, a fee — the intake must appear
       in the archived page, and the question is then asked about that intake (DD-009).

All are substring tests over the snapshot; no model judges them. A fabricated quote, or a
value that does not come from the quoted text, is discarded automatically.

Check 5 is deliberately weaker than the others: the intake is matched against the whole
page rather than the quote, because on a fee table the year is a heading above the
figures. It scopes the question rather than answering it, and the reviewer sees it.

## Guarding the human step

Some candidates are attention checks. An earlier design shifted a digit, which broke
the machine-checked "value appears in the quote" property — so it tested the reviewer on
something the pipeline already catches, and produced no visual cue. It was missed in
review, deservedly.

A check now substitutes a *different real number from the same sentence*. All mechanical
checks still pass and the value is still highlighted; the only way to catch it is to read
the sentence and ask what was requested. That is the step being measured. The catch rate
is reported in the paper alongside the acceptance rate — without it, "a human verified
it" is a claim with nothing behind it.

Only quotes containing a second number can carry a check, so they are less frequent than
the nominal rate. Fewer, but measuring the right thing.

## Who extracts

The extractor model is excluded from the models under test — otherwise a model would be
graded against a standard it wrote. Set in EXTRACTOR below and recorded on every
candidate.
"""

import argparse
import csv
import hashlib
import html
import json
import os
import random
import re
import sys
import time
import urllib.error
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from new_item import FACTS, LEVELS, PROGRAMS, UNIVERSITIES  # noqa: E402
from qualifiers import TEST_FAMILIES, families_for, family_of  # noqa: E402
from run_eval import http_post_json                # noqa: E402

PAGES = Path("data/pages.csv")
CANDIDATES = Path("data/candidates.jsonl")
SNAPSHOTS = Path("data/snapshots")

# Excluded from the evaluated models. Chosen for the highest free-tier daily quota,
# since extraction is many long inputs rather than many short ones.
EXTRACTOR = "gemini-3.5-flash-lite"

# Share of candidates deliberately corrupted to test whether the reviewer is reading.
CONTROL_RATE = 0.05
CONTROL_SEED = 20260808

# Each row of data/pages.csv is one page plus the facts to look for on it. Fixed page
# roles were tried first and did not survive contact with real sites: a university may
# state its TOEFL minimum on one page, its fee on another, and its deadline on a third.
# Listing the facts per page is what lets the extractor be asked a narrow question.
DEFAULT_FACT_SETS = {
    "admissions": "deadline,documents,eligibility",
    "fees": "tuition",
    "english": "english",
    "program": "language,duration",
    "about": "city",
}
MAX_PAGE_CHARS = 40000   # a long admissions page fits; beyond this it is navigation cruft

# Minimum characters the quote must carry beyond the value itself. Below this the
# "quote" is just the value repeated, and the human review has nothing to verify.
MIN_QUOTE_CONTEXT = 20


def page_text(path):
    """Visible text of an archived page, with scripts and markup removed."""
    raw = Path(path).read_text(encoding="utf-8", errors="replace")
    raw = re.sub(r"(?is)<(script|style|noscript|svg).*?</\1>", " ", raw)
    text = html.unescape(re.sub(r"(?s)<[^>]+>", " ", raw))
    return re.sub(r"[ \t ]+", " ", re.sub(r"\n\s*\n+", "\n", text)).strip()


def _fold(text):
    """Character-level folding shared by normalise and its index-tracking twin."""
    text = text.replace("\u2019", "'").replace("\u2018", "'")
    text = text.replace("\u201c", '"').replace("\u201d", '"')
    return text.replace("\u2013", "-").replace("\u2014", "-").replace("\u00a0", " ")


def normalise(text):
    """Loose form for substring checks: collapse whitespace, drop case and quote style."""
    return re.sub(r"\s+", " ", _fold(text)).strip().lower()


def normalise_indexed(text):
    """normalise(), plus the original index each surviving character came from.

    Needed to widen a quote back out into the raw page: a match is found in the
    normalised text, and the span has to be cut from the text a person will read.
    """
    folded = _fold(text).lower()
    out, index, previous_space = [], [], True
    for position, char in enumerate(folded):
        if char.isspace():
            if previous_space:
                continue
            out.append(" ")
            index.append(position)
            previous_space = True
        else:
            out.append(char)
            index.append(position)
            previous_space = False
    while out and out[-1] == " ":
        out.pop()
        index.pop()
    return "".join(out), index


# How far either side of a quote the qualifier may be found before the candidate is
# dropped. A fee and the words "per term" sit in neighbouring cells of one table row;
# a fee and a period from a different table are not each other's.
WIDEN_WINDOW = 320


def widen(quote, qual, page, page_norm, page_index, fact=None):
    """Return a quote extended to contain `qual`, or None if it is not close by.

    The qualifier is half the answer -- "$33,360" alone answers nothing -- so it has to
    be inside the quote a reviewer reads, not merely somewhere on the page. But pages put
    the amount in one cell and its period in the next, so the extractor cannot always
    produce one quote holding both, and requiring it discarded fifteen of twenty-two
    candidates in a single run.

    Widening is done here, from the archived bytes, by substring arithmetic -- the model
    does not get to choose the wider span. The guarantee is unchanged: every part of the
    answer appears inside the quote shown to the person who accepted it.
    """
    needle = normalise(quote)
    at = page_norm.find(needle)
    if at < 0:
        return None
    start, end = at, at + len(needle)

    # Harvard's fee page lists per-course rates and then, four figures later, a note
    # saying students need "a minimum of 2 courses per term". Widening forward found that
    # "per term" and attached it to $8,438, producing "$8,438 per term" — a real number
    # and a real phrase that were never about each other. Anything of the same kind lying
    # between the two means they belong to different rows, and the pair is not evidence.
    INTERVENING = {"tuition": re.compile(r"[$£€¥]\s?\d[\d,. ]{2,}|\b\d[\d,. ]{3,}\s?(?:usd|eur|gbp|chf|sek|aed)\b")}
    barrier = INTERVENING.get(fact)

    # The extractor writes the period in its own words — "per year" — where the page
    # says "Annual fee". Only the page's wording may enter a quote, so search for every
    # wording of the same period, starting with the one the extractor gave. Without this
    # the widening never fired: in a full run it rescued none of the nine candidates it
    # was built for, because none of them matched literally.
    wordings = [normalise(qual)]
    if fact is not None:
        families = families_for(FACTS[fact][0])
        family = family_of(qual, families)
        if family:
            wordings += [normalise(w) for w in families[family]]

    # Gather every candidate position, then take the nearest. Returning the first wording
    # that matched anywhere was how "per term" from a footnote beat "Cost/Term" standing
    # directly above the figure: the literal wording is tried first, and it happened to
    # occur further away.
    found = []
    for target in dict.fromkeys(w for w in wordings if w):
        position = page_norm.rfind(target, max(0, start - WIDEN_WINDOW), start)
        if position >= 0:
            found.append((start - (position + len(target)), position, position + len(target)))
        position = page_norm.find(target, end, end + WIDEN_WINDOW)
        if position >= 0:
            found.append((position - end, position, position + len(target)))

    crossed = False
    for _, at_qual, qual_end in sorted(found):
        span_start, span_end = min(start, at_qual), max(end, qual_end)
        if barrier:
            gap = (page_norm[qual_end:start] if at_qual < start
                   else page_norm[end:at_qual])
            if barrier.search(gap):
                crossed = True
                continue     # another figure sits between them; they are different rows
        # `crossed` means a nearer wording was rejected for having other figures in
        # between, so this value sits inside a table of alternatives — a rate card rather
        # than a programme fee. The code cannot tell "$33,752 per term" (a fee period)
        # from "2 courses per term" (a workload) when nothing numeric separates them, and
        # guessing would be worse than saying so. Flag it and let a person read it.
        return (page[page_index[span_start]:page_index[span_end - 1] + 1].strip(),
                page[page_index[at_qual]:page_index[qual_end - 1] + 1],
                crossed)
    return None



# ---------------------------------------------------------------------------

def init():
    """Create the page list. This is the only place a person supplies input."""
    if PAGES.exists():
        print(f"{PAGES} already exists — leaving it alone.")
        return 0

    from sheet import SOURCES

    rows = []
    for key, (name, country, tier) in UNIVERSITIES.items():
        source = SOURCES.get(key, {})
        for level in LEVELS:
            for role in DEFAULT_FACT_SETS:
                # A level-specific page beats a generic one: an MSc programme page and
                # a BSc programme page state different durations and different fees.
                known = source.get(f"{role}_{level}") or source.get(role)
                rows.append({
                    "university": key, "level": level, "role": role,
                    "facts": DEFAULT_FACT_SETS[role],
                    "url": known or "",
                    "hint": f"https://www.google.com/search?q=site:{source.get('domain','')}+"
                            + {"admissions": "application+deadline+required+documents",
                               "fees": "tuition+fee+per+year+cost",
                               "english": "TOEFL+IELTS+minimum+score+english+language+requirement",
                               "program": "programme+duration+language+of+instruction",
                               "about": "campus+location+city"}[role],
                })

    PAGES.parent.mkdir(parents=True, exist_ok=True)
    with PAGES.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["university", "level", "role", "facts", "url", "hint"])
        writer.writeheader()
        writer.writerows(rows)

    filled = sum(1 for r in rows if r["url"])
    print(f"Created {PAGES}: {len(rows)} rows, {filled} URLs already known.")
    print(f"\nOpen it and paste URLs into the empty `url` cells:")
    print(f"  open -a Numbers {PAGES}")
    print("The `hint` column links to a site-scoped search for each one.")
    print("Rows left blank are skipped — you do not need all of them.")
    print("\nThen:  python3 src/extract.py fetch")
    return 0


def read_pages():
    if not PAGES.exists():
        print(f"{PAGES} not found. Run: python3 src/extract.py init")
        return []
    with PAGES.open(encoding="utf-8-sig", newline="") as f:
        return [r for r in csv.DictReader(f) if (r.get("url") or "").strip().startswith("https://")]


def slug_for(row):
    return f"{row['university']}-{row['level']}-{row['role']}"


def fetch():
    """Archive every page in the list. One snapshot per page, reused by many facts."""
    from collect import fetch as fetch_one, snapshot_path

    rows = read_pages()
    if not rows:
        print("No URLs filled in yet.")
        return 1

    saved = skipped = failed = superseded = 0
    for row in rows:
        slug = slug_for(row)
        existing = snapshot_path(slug)

        if existing.exists():
            # The snapshot name does not depend on the URL, so changing a URL in
            # pages.csv would otherwise leave the old page in place and be silently
            # reused. That is worse than a crash: the benchmark would record the new
            # source_url next to a snapshot of a different page, and the evidence chain
            # would be broken with nothing to show for it. Compare and re-archive.
            sidecar = existing.with_suffix(".json")
            archived_url = None
            if sidecar.exists():
                try:
                    archived_url = json.loads(sidecar.read_text(encoding="utf-8")).get("requested_url")
                except json.JSONDecodeError:
                    pass

            if archived_url == row["url"]:
                skipped += 1
                continue

            # Keep the old capture — it is still evidence of what that page said on
            # that date — but move it out of the way so it cannot be picked up again.
            attic = SNAPSHOTS / "superseded"
            attic.mkdir(parents=True, exist_ok=True)
            for path in (existing, sidecar):
                if path.exists():
                    path.rename(attic / path.name)
            superseded += 1
            print(f"{slug}: URL changed, re-archiving")

        print(f"{slug}: {row['url']}")
        if fetch_one(row["url"], slug):
            saved += 1
        else:
            failed += 1

    print(f"\n{saved} archived, {skipped} unchanged, {superseded} replaced after a URL change, {failed} failed")
    if superseded:
        print(f"  Old captures moved to {SNAPSHOTS / 'superseded'} — kept, but no longer used.")
    print("\nNext:  python3 src/extract.py run")
    return 0


# ---------------------------------------------------------------------------

# Fields whose value means nothing on its own.
#
# MIT states graduate tuition as "$33,360" per term; Cambridge states a figure per year;
# KTH states one for the full programme. Asking for "the annual tuition fee" made the
# page unanswerable wherever the university does not publish an annual figure — the
# extractor correctly returned nothing, since computing it is forbidden. The same held
# for "minimum TOEFL iBT score" at universities that publish only IELTS.
#
# That is worse than lost yield. Publishing convention travels with country and with
# tier, so admitting only universities that happen to publish in the assumed unit makes
# the tier comparison a comparison of publishing conventions. The fix is to ask what the
# page actually states and carry the qualifier into the answer: "$33,360 per term",
# "IELTS 7.0". Both parts are quoted from the page, so both stay machine-checkable.
QUALIFIER = {
    "tuition": ("period", "the period this amount covers, worded exactly as the page "
                          "writes it — 'per year', 'per term', 'per semester', 'for the "
                          "full programme'", "{value} {qual}"),
    "english": ("test", "which test this score belongs to, named exactly as the page "
                        "names it — 'TOEFL iBT', 'IELTS', 'Duolingo'", "{qual} {value}"),
}


# Facts whose value is meaningless without the intake it belongs to, and which pages
# actually stamp with one. The prompt used to fix the cycle at Fall 2027 and order the
# extractor to omit anything else. Universities publish fee tables for the academic year
# now beginning, so MIT's "Fall and spring 2026-2027 ... $33,360" was correctly refused,
# and every fee page refused with it — which is why the annual cells stayed empty while
# the stable ones filled up. The intake is now read off the page and quoted like any
# other part of the answer, and the question is then asked about that intake.
CYCLE_FACTS = {"deadline", "tuition"}

# Facts a university sets for a whole level of study rather than per programme. MIT's
# registrar publishes one graduate tuition for every graduate student; its fee page never
# says "Electrical Engineering and Computer Science". An earlier rule — take nothing the
# page states only "for the institution in general" — was added to stop institution-level
# answers being filed against a programme, and it is right for duration and language,
# which really do differ per programme. Applied to fees and deadlines it refused the very
# pages that carry them.
LEVEL_WIDE = {"tuition", "english", "deadline", "documents", "eligibility", "city"}


def canonical_cycle(raw):
    """Turn a quoted intake — '2026-2027', 'Fall 2027 entry' — into question wording.

    Regex, not a model: the extractor supplies the verbatim string and the checks confirm
    it is on the page, but the phrasing that goes into a question is derived mechanically
    so no unquoted text can reach the benchmark.
    """
    years = re.findall(r"20\d{2}", raw or "")
    if len(years) >= 2 and years[0] != years[1]:
        return f"the {years[0]}–{years[1]} academic year", \
               f"на {years[0]}–{years[1]} учебный год"
    if years:
        return f"Fall {years[0]}", f"осенью {years[0]} года"
    return None


def build_prompt(text, level_en, university, wanted, program, cycle="Fall 2027"):
    lines = "\n".join(
        f"- {fact}: {desc}" + (
            f"\n    also give \"{QUALIFIER[fact][0]}\": {QUALIFIER[fact][1]}"
            if fact in QUALIFIER else ""
        )
        for fact, desc in wanted.items()
    )
    specific = sorted(f for f in wanted if f not in LEVEL_WIDE)
    shared = sorted(f for f in wanted if f in LEVEL_WIDE)
    scope_rule = ""
    if specific:
        scope_rule += f"""
For {', '.join(specific)}: these differ between programmes. Take only what the page
states for {program} itself. If it states them for a different programme, or only in
general terms, omit the field.
"""
    if shared:
        scope_rule += f"""
For {', '.join(shared)}: universities normally set these for all {level_en} applicants
rather than per programme. A value this page states for {level_en} students at
{university} as a whole does apply to {program} — give it, and do not omit it for being
stated generally. If the page also states a different value specifically for {program},
prefer that one. If it is stated for a different level of study, omit it.
"""

    cycle_rule = ""
    if any(f in CYCLE_FACTS for f in wanted):
        stamped = ", ".join(sorted(f for f in wanted if f in CYCLE_FACTS))
        cycle_rule = f"""
For {stamped}, also give "cycle": the intake or academic year the value belongs to,
copied from the page — "2026-2027", "Fall 2027", "2027 entry". It usually sits in the
heading above the table rather than beside the figure; take it from there. Do not work
it out from the page's publication date and do not assume the current year. If the page
nowhere says which intake the value is for, omit the field. Values the page marks as
belonging to a past intake are still wanted; the intake you give is what tells them
apart.
"""
    # A worked example, because the constraints interact in a way that is easy to read as
    # impossible. Asked for a fee, its period and its intake, all quoted, the extractor
    # kept returning [] — the figure sits in one table cell and its period and year in
    # another, so no single narrow quote satisfies everything and the honest response to
    # "omit if you cannot" is to omit. Showing one widened quote that does satisfy it is
    # what turned an empty result into a full one.
    example = ""
    if "tuition" in wanted:
        example = """
Worked example. If the page contains this flattened table row:

    Fall and spring 2026-2027 (per term) Full regular tuition $33,360

then a correct element is:

    {"fact": "tuition", "value": "$33,360", "period": "per term",
     "cycle": "2026-2027",
     "quote": "Fall and spring 2026-2027 (per term) Full regular tuition $33,360"}

The quote was widened to take in the period and the intake as well as the figure. Widen
it the same way whenever the parts sit in neighbouring cells.
"""
    qualified = [f for f in wanted if f in QUALIFIER]
    extra = ""
    if qualified:
        names = ", ".join(f'"{QUALIFIER[f][0]}" (for {f})' for f in qualified)
        extra = f"""
- Some fields above ask for a second part as well: {names}. Give it in the same element.
  It must be copied from the same quote, verbatim, and it must appear inside that quote.
  Do not supply it from your own knowledge and do not normalise it — if the page says
  "per term", write "per term", not "per semester". If the quote does not state it,
  quote a sentence that does, or omit the field.
"""
    return f"""You are reading an archived admissions page from {university}.

Extract facts about {program} at {university}, stated explicitly on this page.
{scope_rule}{cycle_rule}

Fields to look for:
{lines}

Rules, all mandatory:
- Copy the value exactly as the page words it. Do not convert formats or units.
- Give the text from the page that states it, copied VERBATIM, character for character.
  Do not paraphrase, summarise, tidy, or shorten it. It does not have to be a sentence:
  fees, deadlines and test scores are usually published in tables, and a flattened table
  row such as "Fall and spring 2026-2027 (per term) Full regular tuition $33,360" is a
  valid quote. Quote the contiguous run of text that carries both the label and the
  value, so the two can be seen to belong together.
- The value you give must appear inside the quote you give.
- If a field is not stated explicitly on this page, omit it entirely. Do not infer it,
  do not compute it, and do not use anything you know from outside this page.
- If the page states several values for one field — tiered fees, per-programme
  requirements, different deadlines per round — return every one of them as a separate
  element. Do not choose between them and do not skip the field. A person decides
  afterwards whether the fact is well defined enough to use.
- "fact" must be exactly one of the field names listed above, spelled identically.
  Do not invent field names and do not describe the field in prose.
{extra}
{example}
Return a JSON array. Each element: {{"fact": "<field name>", "value": "<the value>",
"quote": "<verbatim text>"}}, plus the extra parts named above where they are asked for.
Return [] if nothing qualifies.

PAGE TEXT:
{text}
"""


FIELD_HINTS = {
    "deadline": "the final application deadline date for this admissions cycle",
    "tuition": "the tuition fee as this page states it, with its currency",
    "english": "the minimum English language test score required",
    "documents": "how many recommendation letters or referees are required",
    "eligibility": "the minimum academic requirement to apply — a GPA, a degree classification, or a percentage, whichever the page states",
    "language": "the language of instruction",
    "duration": "how long the programme takes",
    "city": "the city of the main campus",
}


def call_extractor(text, level_en, university, wanted, program, cycle="Fall 2027"):
    key = os.environ.get("GEMINI_API_KEY")
    if not key:
        raise RuntimeError("GEMINI_API_KEY is not set")

    body = http_post_json(
        f"https://generativelanguage.googleapis.com/v1beta/models/{EXTRACTOR}:generateContent?key={key}",
        {
            "contents": [{"parts": [{"text": build_prompt(text, level_en, university, wanted, program, cycle)}]}],
            "generationConfig": {"responseMimeType": "application/json", "maxOutputTokens": 4096},
        },
    )
    # "Nothing extracted" and "the call did not work" used to look identical here: both
    # returned []. A whole batch of institutions reported 0 candidates and 0 discards,
    # which reads as "these pages have no facts" and is the one message that stops you
    # looking. Return the reason alongside the items so a silent failure has to announce
    # itself.
    candidates = body.get("candidates") or []
    if not candidates:
        blocked = (body.get("promptFeedback") or {}).get("blockReason")
        return [], f"no candidates in response ({blocked or 'no reason given'})"

    finish = candidates[0].get("finishReason")
    raw = "".join(p.get("text", "") for p in candidates[0].get("content", {}).get("parts", []))
    if not raw.strip():
        return [], f"empty text (finishReason={finish})"
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        cut = "; output was cut off" if finish == "MAX_TOKENS" else ""
        return [], f"response was not JSON (finishReason={finish}{cut})"
    if not isinstance(parsed, list):
        return [], f"response was {type(parsed).__name__}, expected a list"
    return parsed, None


# Patterns taken from the reasons a reviewer actually rejected candidates in the first
# sitting. Each one is a phrase that makes the quoted sentence state something other
# than what the question asks — a bound rather than a value, a different admissions
# round, a fee in different units. Catching them here means the reviewer sees plausible
# candidates instead of spending attention on obvious misses.
SUSPECT = {
    "bound": (
        ["maximum", "at most", "up to", "no more than", "at least", "minimum of",
         "not exceed", "maximum candidature"],
        "states a limit, not the value asked for",
    ),
    "wrong_round": (
        ["early action", "early decision", "funding deadline", "scholarship deadline",
         "gates ", "restrictive early"],
        "belongs to a different application round",
    ),
    "wrong_unit": (
        ["per semester", "per term", "full programme", "full program", "total programme",
         "entire programme", "per credit", "per module"],
        "states the fee in different units than the annual figure asked for",
    ),
    "conditional": (
        ["depending on", "varies by", "or higher", "respectively"],
        "the value depends on something the question does not specify",
    ),
}

# Which suspicion applies to which field. A duration quote mentioning "maximum" is
# suspect; a document-count quote mentioning "at least" is fine, because the question is
# about how many are required.
SUSPECT_FOR = {
    "duration": ["bound", "conditional"],
    "deadline": ["wrong_round", "conditional"],
    # "wrong_unit" was dropped once the period became part of the answer. It flagged
    # "per semester" as suspect, which was only true while the question presumed an
    # annual figure; now the unit is quoted rather than assumed, and a per-semester fee
    # is a correct answer to a question that asks what the page states.
    "tuition": ["conditional"],
    "english": ["conditional"],
    "documents": ["bound"],
    "eligibility": ["conditional"],
}


def compose(fact, value, qual):
    """The answer a reviewer judges and the benchmark stores.

    Kept separate from `value` because the mechanical checks work on the parts: each of
    "$33,360" and "per term" is a substring of the quote, while "$33,360 per term" is not
    — the page writes them either side of other words. Composing after the checks keeps
    the answer readable without weakening what was verified.
    """
    if fact in QUALIFIER and qual:
        return QUALIFIER[fact][2].format(value=value, qual=qual)
    return value


MONEY = re.compile(r"[$£€¥]\s?\d[\d,. ]{2,}|\b\d[\d,. ]{3,}\s?(?:usd|eur|gbp|chf|sek|aed)\b",
                   re.I)


def suspicions(fact, quote, value):
    """Reasons this candidate probably answers a different question. Advisory only."""
    found, lowered = [], quote.lower()
    for name in SUSPECT_FOR.get(fact, []):
        phrases, reason = SUSPECT[name]
        if any(phrase in lowered for phrase in phrases):
            found.append(reason)

    # Harvard's fee page lists a rate card — one course $8,438, two $16,876, three
    # $25,314, four $33,752 — followed by a note about needing "2 courses per term".
    # Two candidates came out of it pairing a per-course rate with that note's period,
    # and both were real figures in real text. Nothing mechanical separates a fee period
    # from a workload period here, so the honest move is to tell the reviewer the quote
    # holds a choice of amounts rather than a single one.
    if fact == "tuition" and len(MONEY.findall(quote)) > 1:
        found.append("the quote lists several amounts — check this is the one the "
                     "question asks for, and that the period belongs to it")

    # The same failure with test names. "an overall IELTS score of 6.5 or a TOEFL score
    # of 4.5" yielded "IELTS 4.5", and "a minimum score of 7 on the IELTS Academic test
    # and a minimum Speaking score of 6.5" yielded "IELTS 6.5" — the speaking sub-score.
    # One sentence, two tests or two scores, and the pairing is a guess.
    if fact == "english":
        tests = {name for name, wordings in TEST_FAMILIES.items()
                 if any(w in lowered for w in wordings)}
        if len(tests) > 1:
            found.append("the quote names more than one test — check the score belongs "
                         "to the test given, not the other one")
        elif len(re.findall(r"\b\d{1,3}(?:\.\d)?\b", quote)) > 1:
            found.append("the quote states more than one score — check this is the "
                         "overall minimum, not a sub-score or an older scale")
    return found


def corrupt(value, quote, rng):
    """Build an attention-check control: a real value from the quote that answers the
    wrong question.

    The first design shifted a digit — `2 years` became `4 years`. That broke the
    machine-checked property "the value appears inside the quote", so the control was
    testing the reviewer on something the pipeline already verifies, and it produced no
    visual cue in the interface (the highlighter cannot mark a value that is not there).
    It was missed in review, and rightly so.

    A control has to test what only a person can do: judge whether the value answers the
    question. So take a *different real number* from the same sentence. Every mechanical
    check still passes, the highlighter still marks it, and the only way to catch it is
    to read the sentence and think about what was asked — which is exactly the step
    being measured.
    """
    numbers = re.findall(r"\d[\d,.]*", quote)
    alternatives = [n for n in numbers if n not in value and len(n) >= 1]
    if not alternatives:
        return None
    return rng.choice(alternatives)


LEDGER = Path("data/extraction_log.jsonl")


def ledger_key(slug, snapshot, asked):
    """What makes an extraction call worth repeating.

    A call is determined by the archived bytes and the fields requested, so if neither
    changed, calling again can only produce what the content-level dedupe throws away.
    The snapshot digest rather than its name: re-archiving a page that has since changed
    writes the same filename, and that call *is* worth making again.
    """
    digest = hashlib.sha256(snapshot.read_bytes()).hexdigest()[:16]
    return f"{slug}|{digest}|{','.join(sorted(asked))}"


def load_ledger():
    done = {}
    if LEDGER.exists():
        for line in LEDGER.read_text(encoding="utf-8").splitlines():
            if line.strip():
                entry = json.loads(line)
                done[entry["key"]] = entry
    return done


def run(force=False, only=None):
    rows = read_pages()
    if not rows:
        return 1

    from collect import snapshot_path

    existing, seen_content, decided = set(), set(), 0
    if CANDIDATES.exists():
        for line in CANDIDATES.read_text(encoding="utf-8").splitlines():
            if line.strip():
                row = json.loads(line)
                existing.add(row["id"])
                # Identity is the fact plus what was said about it. Keying only on the
                # id let a second run re-propose a byte-identical candidate under an
                # -alt suffix, so the reviewer judged the same sentence twice and the
                # duplicate then looked like a conflict at import time.
                seen_content.add((row.get("base_id", row["id"]),
                                  normalise(row["value"]), normalise(row["quote"])))
                decided += bool(row.get("decision"))

    # This appends and skips ids already present, so re-running never loses a decision.
    # What does lose them is deleting the file first — that happened twice during
    # development while chasing clean yield numbers, and cost the reviewer their work
    # both times. Never `rm` this file to get a fresh count; the counts below are per-run
    # already. Say plainly what is being kept so the safety is visible rather than
    # assumed.
    if decided:
        print(f"{CANDIDATES}: {len(existing)} candidate(s), {decided} already reviewed — "
              f"these are kept and skipped.\n")

    # The same URL listed for both levels means one level's facts get attributed to the
    # other: a page about the bachelor's programme will happily yield a "duration" that
    # is then filed as a master's fact. Observed on MBZUAI during testing. This is a
    # silent error — the quote is real and the checks pass — so warn before extracting.
    # `about` legitimately serves both levels — the campus city does not depend on the
    # degree. Only flag pages whose facts are level-specific.
    LEVEL_SENSITIVE = {"admissions", "fees", "english", "program"}
    by_url = {}
    for row in rows:
        if row["role"] in LEVEL_SENSITIVE:
            by_url.setdefault((row["url"], row["role"]), set()).add(row["level"])
    shared = [(url, role) for (url, role), levels in by_url.items() if len(levels) > 1]
    if shared:
        print(f"warning: {len(shared)} page(s) are listed for both levels. Facts from them")
        print("  will be attributed to whichever level the row says, which may be wrong:")
        for url, role in shared[:6]:
            print(f"    {role}: {url}")
        print("  Fix the level-specific rows in data/pages.csv, or reject those candidates.\n")

    # Every run used to call the extractor on all 103 archived pages, because duplicates
    # were only detected from the *response*. The request was spent either way, so a run
    # that produced nothing new still consumed the day's free quota, and the last
    # institutions in the list were never reached. Record what has been asked, and ask
    # only for what is new.
    done = load_ledger()
    skipped_done = 0

    rng = random.Random(CONTROL_SEED)
    produced = rejected_quote = rejected_value = rejected_context = controls = 0
    rejected_qualifier = rejected_cycle = widened = 0
    duplicates = unusable = 0

    CANDIDATES.parent.mkdir(parents=True, exist_ok=True)
    LEDGER.parent.mkdir(parents=True, exist_ok=True)
    with CANDIDATES.open("a", encoding="utf-8") as out, \
            LEDGER.open("a", encoding="utf-8") as log:
        for row in rows:
            slug = slug_for(row)
            snapshot = snapshot_path(slug)
            if not snapshot.exists():
                continue
            if only and not any(part in slug for part in only):
                continue

            text = page_text(snapshot)
            haystack, haystack_index = normalise_indexed(text)
            level_en = LEVELS[row["level"]][0]
            university = UNIVERSITIES[row["university"]][0]

            # Only ask for the fields this kind of page plausibly carries.
            asked = [f.strip() for f in (row.get("facts") or "").split(",") if f.strip()]
            wanted = {f: FIELD_HINTS[f] for f in asked if f in FACTS}
            if not wanted:
                continue

            key = ledger_key(slug, snapshot, wanted)
            if not force and key in done:
                skipped_done += 1
                continue

            print(f"{slug} ... ", end="", flush=True)
            try:
                found, note = call_extractor(text[:MAX_PAGE_CHARS], level_en, university,
                                            wanted,
                                            PROGRAMS[row["university"]][row["level"]])
            except urllib.error.HTTPError as exc:
                detail = exc.read().decode("utf-8", "replace")
                # A free tier answers 429 both for "too fast" and "done for today", and
                # only the message tells them apart. Continuing past a daily cap walks
                # the whole page list making failing calls and printing nothing useful;
                # stop instead, keep what was written, and say when to come back.
                if exc.code == 429 and ("PerDay" in detail or "per day" in detail.lower()):
                    print("daily quota reached")
                    print(f"\n{produced} candidate(s) written before the cap.")
                    print("The free tier resets daily — re-run tomorrow and it will "
                          "continue from where it stopped.")
                    return 0
                print(f"failed (HTTP {exc.code})")
                continue
            except Exception as exc:
                print(f"failed ({str(exc)[:80]})")
                continue

            kept = 0
            for entry in found:
                fact = str(entry.get("fact", "")).strip()
                value = str(entry.get("value", "")).strip()
                quote = str(entry.get("quote", "")).strip()
                if fact not in wanted or not value or not quote:
                    continue

                base_id = f"{row['university']}-{row['level']}-{fact}"
                fingerprint = (base_id, normalise(value), normalise(quote))
                if fingerprint in seen_content:
                    duplicates += 1
                    continue
                item_id, suffix = base_id, 2
                while item_id in existing:
                    item_id = f"{base_id}-alt{suffix}"
                    suffix += 1
                    if suffix > 6:      # a page listing seven values is not a usable fact
                        break
                if item_id in existing:
                    continue

                # Check 1: the quote must really be on the page.
                if normalise(quote) not in haystack:
                    rejected_quote += 1
                    continue
                # Check 2: the value must come from that sentence.
                if normalise(value) not in normalise(quote):
                    rejected_value += 1
                    continue
                # Check 3: the quote must carry context beyond the value itself.
                # A "quote" identical to the value gives a reviewer nothing to check
                # against — they would be confirming the value with the value. Require
                # the sentence to say what the number *is*, not just repeat it.
                if len(normalise(quote)) < len(normalise(value)) + MIN_QUOTE_CONTEXT:
                    rejected_context += 1
                    continue
                # Check 4, for fields whose value means nothing alone: the qualifier is
                # held to the same standard as the value. Without it, the one part of the
                # gold answer nobody checked would be the part supplied from the model's
                # own knowledge — the line this pipeline does not cross.
                qual, was_widened, extra_flags = "", False, []
                if fact in QUALIFIER:
                    qual = str(entry.get(QUALIFIER[fact][0], "")).strip()
                    if not qual:
                        rejected_qualifier += 1
                        continue
                    if normalise(qual) not in normalise(quote):
                        # Widening only ever grows the span, so checks 1-3 still hold on
                        # the result and the value is still inside it. The qualifier is
                        # replaced by the page's own wording of the same period, which is
                        # the only wording allowed to appear in a quote.
                        wider = widen(quote, qual, text, haystack, haystack_index, fact)
                        if wider is None:
                            rejected_qualifier += 1
                            continue
                        quote, qual = wider[0], wider[1].strip()
                        was_widened = True
                        if wider[2]:
                            extra_flags.append(
                                "the period may belong to a different row — this figure "
                                "sits among several others on the page")
                cycle_raw = cycle_en = cycle_ru = ""
                if fact in CYCLE_FACTS:
                    # Checked against the page, not the quote. The intake is normally a
                    # heading above the fee table, so demanding it inside the same quote
                    # made most fee pages unextractable. It is still verbatim from the
                    # archive, and unlike the value it scopes the question rather than
                    # answering it — the reviewer sees it and rejects a wrong year.
                    cycle_raw = str(entry.get("cycle", "")).strip()
                    if not cycle_raw or normalise(cycle_raw) not in haystack:
                        rejected_cycle += 1
                        continue
                    phrasing = canonical_cycle(cycle_raw)
                    if phrasing is None:
                        rejected_cycle += 1
                        continue
                    cycle_en, cycle_ru = phrasing

                is_control, shown = False, value
                if rng.random() < CONTROL_RATE:
                    altered = corrupt(value, quote, rng)
                    if altered and altered != value:
                        is_control, shown = True, altered
                        controls += 1

                # Advisory, not a filter: a suspected candidate is still shown, marked,
                # because the reviewer sometimes overrules the heuristic and a silent
                # drop would hide that. Controls are never marked — that would give them
                # away and the check would stop measuring anything.
                flags = [] if is_control else suspicions(fact, quote, shown) + extra_flags

                out.write(json.dumps({
                    "id": item_id,
                    "suspicions": flags,
                    "base_id": base_id,
                    "university": row["university"],
                    "level": row["level"],
                    "fact": fact,
                    "value": shown,
                    "qualifier": qual,
                    "quote_widened": was_widened,
                    "cycle_quoted": cycle_raw,
                    "cycle_en": cycle_en,
                    "cycle_ru": cycle_ru,
                    "answer": compose(fact, shown, qual),
                    "true_value": value if is_control else None,
                    "quote": quote,
                    "source_url": row["url"],
                    "snapshot_path": str(snapshot),
                    "extractor": EXTRACTOR,
                    "extracted_at": date.today().isoformat(),
                    "is_control": is_control,
                    "decision": None,
                }, ensure_ascii=False) + "\n")
                existing.add(item_id)
                seen_content.add(fingerprint)
                kept += 1
                produced += 1

            # Written only after the call returned, so a run interrupted mid-page repeats
            # that page rather than silently skipping it next time.
            log.write(json.dumps({
                "key": key, "slug": slug, "facts": sorted(wanted),
                "returned": len(found), "kept": kept,
                "extractor": EXTRACTOR, "at": date.today().isoformat(),
            }, ensure_ascii=False) + "\n")
            log.flush()

            if note:
                print(f"{kept} candidate(s)  [{note}]")
                unusable += 1
            else:
                print(f"{kept} candidate(s)")
            time.sleep(4)   # free-tier pacing

    print(f"\n{produced} candidate(s) written to {CANDIDATES}")
    if skipped_done:
        print(f"  {skipped_done} page(s) skipped: already extracted from the same "
              f"snapshot for the same fields (--force to redo)")
    print(f"  {rejected_quote} discarded: quote not found in the archived page")
    print(f"  {rejected_value} discarded: value not inside its own quote")
    print(f"  {rejected_context} discarded: quote had no context beyond the value itself")
    if rejected_qualifier:
        print(f"  {rejected_qualifier} discarded: the period or test name was missing "
              f"from the quote")
    if widened:
        print(f"  {widened} quote(s) widened from the archive to take in the period "
              f"or test name")
    if rejected_cycle:
        print(f"  {rejected_cycle} discarded: the quote did not say which intake the "
              f"value is for")
    print(f"  {duplicates} skipped: already proposed with the same value and quote")
    if unusable:
        print(f"  {unusable} page(s) returned nothing usable — see the bracketed "
              f"reason above; that is a pipeline fault, not an empty page")
    print(f"  {controls} of the kept candidates are deliberately corrupted controls")
    print("\nNext:  python3 src/verify.py")
    return 0


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("command", choices=["init", "fetch", "run"])
    parser.add_argument("--force", action="store_true",
                        help="re-extract pages already in the ledger")
    parser.add_argument("--only", metavar="SUBSTRINGS",
                        help="comma-separated; restrict to page slugs containing any of "
                             "them, e.g. --only mit,kaist. Use it to spend a limited "
                             "daily quota on the cells the design is short of.")
    args = parser.parse_args()
    if args.command == "run":
        only = [s.strip() for s in args.only.split(",")] if args.only else None
        return run(force=args.force, only=only)
    return {"init": init, "fetch": fetch}[args.command]()


if __name__ == "__main__":
    sys.exit(main())
