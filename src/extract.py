"""Propose fact candidates from archived pages, for a human to accept or reject.

    python3 src/extract.py init     # create data/pages.csv — paste URLs into it
    python3 src/extract.py fetch    # archive every page listed there
    python3 src/extract.py run      # propose candidates from the archives

Then review them: python3 src/verify.py

## The line this pipeline does not cross

A model never supplies a gold answer from memory. It is shown an archived page and asked
to copy a fact and the sentence that states it out of that page. Extraction from a
document in front of the model is a different task from recall, and the output is not
trusted on its own: every candidate passes two deterministic checks before a person ever
sees it, and a person then accepts or rejects it against the quote.

    1. The quote must appear verbatim in the archived page.
    2. The extracted value must appear inside the quote.

Both are substring tests over the snapshot — no model involved. A fabricated quote or a
value that does not come from the quoted sentence is discarded automatically.

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


def normalise(text):
    """Loose form for substring checks: collapse whitespace, drop case and quote style."""
    text = text.replace("’", "'").replace("‘", "'")
    text = text.replace("“", '"').replace("”", '"')
    text = text.replace("–", "-").replace("—", "-").replace(" ", " ")
    return re.sub(r"\s+", " ", text).strip().lower()


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

def build_prompt(text, level_en, university, wanted, program, cycle="Fall 2027"):
    lines = "\n".join(
        f"- {fact}: {desc}" for fact, desc in wanted.items()
    )
    return f"""You are reading an archived admissions page from {university}.

Extract ONLY facts about {program} at {university}, stated explicitly on this page.

The admissions cycle in question is {cycle}. Deadlines, fees and test requirements are
asked about that cycle specifically. Pages often still show the previous cycle: if a
date or figure belongs to an earlier intake, omit it rather than offering it. Only give
a cycle-dependent value when the page ties it to {cycle}.

If the page covers several programmes, take only the values that apply to {program}.
If it never mentions that programme, and the value you would give belongs to a different
programme or to the institution in general, omit the field.

Fields to look for:
{lines}

Rules, all mandatory:
- Copy the value exactly as the page words it. Do not convert formats or units.
- Give the sentence from the page that states it, copied VERBATIM, character for
  character. Do not paraphrase, summarise, tidy, or shorten it.
- The value you give must appear inside the quote you give.
- If a field is not stated explicitly on this page, omit it entirely. Do not infer it,
  do not compute it, and do not use anything you know from outside this page.
- If the page states several values for one field — tiered fees, per-programme
  requirements, different deadlines per round — return every one of them as a separate
  element. Do not choose between them and do not skip the field. A person decides
  afterwards whether the fact is well defined enough to use.
- "fact" must be exactly one of the field names listed above, spelled identically.
  Do not invent field names and do not describe the field in prose.

Return a JSON array. Each element: {{"fact": "<field name>", "value": "<the value>",
"quote": "<verbatim sentence>"}}. Return [] if nothing qualifies.

PAGE TEXT:
{text}
"""


FIELD_HINTS = {
    "deadline": "the final application deadline date for this admissions cycle",
    "tuition": "annual tuition fee, with its currency",
    "english": "minimum TOEFL iBT score required",
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
    candidates = body.get("candidates") or []
    if not candidates:
        return []
    raw = "".join(p.get("text", "") for p in candidates[0].get("content", {}).get("parts", []))
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        return []
    return parsed if isinstance(parsed, list) else []


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
    "tuition": ["wrong_unit", "conditional"],
    "english": ["conditional"],
    "documents": ["bound"],
    "eligibility": ["conditional"],
}


def suspicions(fact, quote, value):
    """Reasons this candidate probably answers a different question. Advisory only."""
    found, lowered = [], quote.lower()
    for name in SUSPECT_FOR.get(fact, []):
        phrases, reason = SUSPECT[name]
        if any(phrase in lowered for phrase in phrases):
            found.append(reason)
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


def run():
    rows = read_pages()
    if not rows:
        return 1

    from collect import snapshot_path

    existing, decided = set(), 0
    if CANDIDATES.exists():
        for line in CANDIDATES.read_text(encoding="utf-8").splitlines():
            if line.strip():
                row = json.loads(line)
                existing.add(row["id"])
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

    rng = random.Random(CONTROL_SEED)
    produced = rejected_quote = rejected_value = rejected_context = controls = 0

    CANDIDATES.parent.mkdir(parents=True, exist_ok=True)
    with CANDIDATES.open("a", encoding="utf-8") as out:
        for row in rows:
            slug = slug_for(row)
            snapshot = snapshot_path(slug)
            if not snapshot.exists():
                continue

            text = page_text(snapshot)
            haystack = normalise(text)
            level_en = LEVELS[row["level"]][0]
            university = UNIVERSITIES[row["university"]][0]

            # Only ask for the fields this kind of page plausibly carries.
            asked = [f.strip() for f in (row.get("facts") or "").split(",") if f.strip()]
            wanted = {f: FIELD_HINTS[f] for f in asked if f in FACTS}
            if not wanted:
                continue

            print(f"{slug} ... ", end="", flush=True)
            try:
                found = call_extractor(text[:MAX_PAGE_CHARS], level_en, university, wanted,
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
                flags = [] if is_control else suspicions(fact, quote, shown)

                out.write(json.dumps({
                    "id": item_id,
                    "suspicions": flags,
                    "base_id": base_id,
                    "university": row["university"],
                    "level": row["level"],
                    "fact": fact,
                    "value": shown,
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
                kept += 1
                produced += 1

            print(f"{kept} candidate(s)")
            time.sleep(4)   # free-tier pacing

    print(f"\n{produced} candidate(s) written to {CANDIDATES}")
    print(f"  {rejected_quote} discarded: quote not found in the archived page")
    print(f"  {rejected_value} discarded: value not inside its own quote")
    print(f"  {rejected_context} discarded: quote had no context beyond the value itself")
    print(f"  {controls} of the kept candidates are deliberately corrupted controls")
    print("\nNext:  python3 src/verify.py")
    return 0


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("command", choices=["init", "fetch", "run"])
    args = parser.parse_args()
    return {"init": init, "fetch": fetch, "run": run}[args.command]()


if __name__ == "__main__":
    sys.exit(main())
