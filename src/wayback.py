"""Find last year's version of each page, for the prior_year_answer column.

    python3 src/wayback.py                    # for every page_url in the sheet
    python3 src/wayback.py --months 18        # look further back
    python3 src/wayback.py --url https://...  # just one page

Queries the Internet Archive for a copy of each page from roughly a year ago and prints
the link. You then open that link and read the previous cycle's value off it, the same
way you read the current one off the live page.

Why this field is worth the trouble: it is what separates a model that is *out of date*
from one that is *inventing*. Without it, a wrong answer is just wrong. With it, a wrong
answer that matches last year's value is a diagnosis. No other benchmark in this area
makes that distinction, and it is the part of this study nobody else is doing.

Nothing here reads the page for you — it only finds where the old copy lives.
"""

import argparse
import csv
import json
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import date, timedelta
from pathlib import Path

SHEET = Path("data/annotation_sheet.csv")
API = "http://archive.org/wayback/available"
TIMEOUT = 25


def find(url, months_back):
    """Ask the Internet Archive for the copy closest to a target date.

    Returns (archived_url, archived_date) or (None, reason). The API returns the nearest
    capture to the timestamp, which may be off by months — the returned date says how
    far off, and that matters: a capture from two months ago is the current cycle, not
    the previous one.
    """
    target = (date.today() - timedelta(days=30 * months_back)).strftime("%Y%m%d")
    query = urllib.parse.urlencode({"url": url, "timestamp": target})
    data = None
    # The availability API rate-limits aggressively and answers 429 well before any
    # reasonable batch is done. A 429 is not a failure, it is "come back in a moment" —
    # treat it that way, or nine lookups in a row all report "failed" and the whole
    # phase looks broken when it is merely impatient.
    for pause in (0, 20, 45, 90):
        if pause:
            time.sleep(pause)
        try:
            with urllib.request.urlopen(f"{API}?{query}", timeout=TIMEOUT) as response:
                data = json.loads(response.read().decode("utf-8"))
            break
        except urllib.error.HTTPError as exc:
            if exc.code == 429:
                continue
            return None, f"lookup failed (HTTP {exc.code})"
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
            return None, f"lookup failed ({exc})"
    if data is None:
        return None, "lookup failed (rate-limited after retries)"

    snapshot = (data.get("archived_snapshots") or {}).get("closest")
    if not snapshot or not snapshot.get("available"):
        return None, "no archived copy"

    stamp = snapshot.get("timestamp", "")
    pretty = f"{stamp[0:4]}-{stamp[4:6]}-{stamp[6:8]}" if len(stamp) >= 8 else stamp
    return snapshot["url"], pretty


def prior_cycle_url(url):
    """The same page one admissions cycle earlier, for URLs that carry the cycle.

    Only fires on a consecutive year pair ("2026-2027", "2026/2027"); a lone year is too
    ambiguous to rewrite mechanically, and a wrong guess here would archive some other
    page under a prior-year label.
    """
    match = re.search(r"(20\d{2})([-–—/_]|%e2%80%93)(20\d{2})", url, re.I)
    if not match:
        return None
    first, second = int(match.group(1)), int(match.group(3))
    if second != first + 1:
        return None
    return (url[:match.start(1)] + str(first - 1) + match.group(2)
            + str(second - 1) + url[match.end(3):])


def rows_from_sheet():
    if not SHEET.exists():
        print(f"{SHEET} not found. Create it with: python3 src/sheet.py make")
        return []
    with SHEET.open(encoding="utf-8-sig", newline="") as f:
        return [r for r in csv.DictReader(f)
                if (r.get("page_url") or "").strip() and r.get("volatility") == "annual"]


BENCHMARK = Path("data/benchmark.jsonl")
PRIOR_DIR = Path("data/snapshots/prior")

# fact_type as stored on benchmark items -> the fact key extract.py works in.
FACT_KEY = {"deadline": "deadline", "tuition": "tuition",
            "test_requirement": "english", "document_list": "documents"}


def needing_prior():
    rows = [json.loads(l) for l in BENCHMARK.read_text(encoding="utf-8").splitlines()
            if l.strip()]
    return rows, [r for r in rows if r.get("volatility") == "annual"
                  and not r.get("prior_year_answer") and r["fact_type"] in FACT_KEY]


def fill(months_back):
    """Propose prior-year values from archived copies, for a person to accept.

    The same protocol as the current-year pipeline, pointed at the Internet Archive:
    find the capture from about a year ago, download it, ask the extractor for the same
    fact, check value and quote by substring against the archived bytes, and put the
    result in front of a person. A model still never supplies a value from memory —
    the only thing that changed is which copy of the official page it reads.

    The capture is saved under data/snapshots/prior/, so the prior value is as
    reproducible as the current one: every number in the dataset traces to bytes on
    disk, whichever year those bytes are from.

    Two phases on purpose. Downloads are free and happen for everything first; extractor
    calls spend the daily quota and stop cleanly at the cap, so an interrupted run
    resumes tomorrow with the downloads already on disk.
    """
    sys.path.insert(0, str(Path(__file__).parent))
    from collect import HEADERS, scrub
    from extract import (FIELD_HINTS, MAX_PAGE_CHARS, call_extractor, normalise,
                         page_text)
    from new_item import LEVELS, PROGRAMS, UNIVERSITIES

    rows, todo = needing_prior()
    if not todo:
        print("Every annual item already has a prior_year_answer (or none qualify).")
        return 0
    print(f"{len(todo)} annual item(s) missing a prior-year value.\n")

    # Phase 1: find and download the year-old captures. No quota involved.
    PRIOR_DIR.mkdir(parents=True, exist_ok=True)
    captures = {}
    for item in todo:
        existing = next(PRIOR_DIR.glob(f"{item['id']}-*.html"), None)
        if existing:
            captures[item["id"]] = existing
            continue

        # A year-stamped URL never archives its way into last year: the Wayback copy of
        # cost-attendance-2026-2027 from any date shows 2026-2027 fees, and extracting
        # from it records "the fact did not change" about a fact that lives at
        # cost-attendance-2025-2026. For those, the previous cycle is a sibling URL —
        # decrement both years and ask the Archive for that page instead.
        lookup_url = prior_cycle_url(item["source_url"]) or item["source_url"]
        if lookup_url != item["source_url"]:
            print(f"  {item['id']}: year-stamped URL, looking for {lookup_url}")

        archived, stamp = find(lookup_url, months_back)
        if not archived:
            print(f"  {item['id']}: {stamp}")
            continue
        # A capture younger than ~9 months documents the current cycle, not the prior
        # one. Recording it would fabricate a "did not change" — worse than a blank.
        if stamp >= (date.today() - timedelta(days=270)).isoformat() \
                and lookup_url == item["source_url"]:
            print(f"  {item['id']}: nearest capture is {stamp} — same cycle, skipped")
            continue
        # `id_` returns the original bytes without the Archive's own banner and
        # rewritten links — the page as the university served it on that day.
        timestamp = archived.split("/web/")[1].split("/")[0]
        raw_url = archived.replace(timestamp, timestamp + "id_", 1)
        try:
            request = urllib.request.Request(raw_url, headers=HEADERS)
            with urllib.request.urlopen(request, timeout=40) as response:
                body = scrub(response.read())
        except Exception as exc:
            print(f"  {item['id']}: download failed ({str(exc)[:50]})")
            continue
        path = PRIOR_DIR / f"{item['id']}-{stamp}.html"
        path.write_bytes(body)
        sidecar = {"item_id": item["id"], "wayback_url": archived, "captured": stamp,
                   "original_url": item["source_url"],
                   "downloaded": date.today().isoformat()}
        path.with_suffix(".json").write_text(json.dumps(sidecar, ensure_ascii=False,
                                                        indent=1), encoding="utf-8")
        captures[item["id"]] = path
        print(f"  {item['id']}: capture from {stamp} saved", flush=True)
        time.sleep(8)   # the Archive rate-limits; slow is the fast path here

    if not captures:
        print("\nNo captures to extract from.")
        return 0

    # Phase 2: extract the same fact from the old copy, checked the same way.
    print(f"\nExtracting from {len(captures)} capture(s):")
    proposals = []
    for item in todo:
        path = captures.get(item["id"])
        if path is None:
            continue
        fact = FACT_KEY[item["fact_type"]]
        uni_key = item["id"].split("-")[0]
        level = item["id"].split("-")[1]
        text = page_text(path)
        print(f"  {item['id']} ... ", end="", flush=True)
        try:
            found, note = call_extractor(text[:MAX_PAGE_CHARS], LEVELS[level][0],
                                         UNIVERSITIES[uni_key][0],
                                         {fact: FIELD_HINTS[fact]},
                                         PROGRAMS[uni_key][level])
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", "replace")
            if exc.code == 429 and ("PerDay" in detail or "per day" in detail.lower()):
                print("daily quota reached — captures are saved, re-run tomorrow")
                break
            print(f"failed (HTTP {exc.code})")
            continue
        kept = []
        for entry in found:
            value = str(entry.get("value", "")).strip()
            quote = str(entry.get("quote", "")).strip()
            if value and quote and normalise(quote) in normalise(text) \
                    and normalise(value) in normalise(quote):
                kept.append((value, quote))
        print(f"{len(kept)} candidate(s)" + (f"  [{note}]" if note else ""))
        for value, quote in kept:
            proposals.append((item, value, quote, path))

    if not proposals:
        print("\nNothing extracted yet.")
        return 0

    # Phase 3: the person decides, exactly as in the main pipeline.
    print(f"\n{len(proposals)} prior-year candidate(s). For each: does the quoted text "
          f"from LAST YEAR'S page state this value?\n")
    by_item = {}
    for item, value, quote, path in proposals:
        by_item.setdefault(item["id"], []).append((item, value, quote, path))

    changed = 0
    for item_id, group in by_item.items():
        item = group[0][0]
        print("=" * 78)
        print(f"  {item_id}")
        print(f"  current gold answer: {item['gold_answer']}")
        for index, (_, value, quote, _) in enumerate(group, start=1):
            print(f"\n  {index}. {value!r}")
            print(f"     {' '.join(quote.split())[:160]}")
        print("\n  Which one is last cycle's value?  [1-N, s to skip]")
        while True:
            choice = input("  > ").strip().lower()
            if choice == "s" or (choice.isdigit() and 1 <= int(choice) <= len(group)):
                break
        if choice == "s":
            continue
        _, value, quote, path = group[int(choice) - 1]
        if value.strip() == str(item["gold_answer"]).strip():
            # An unchanged value is legitimate information, but it belongs in notes:
            # prior == gold would make the item look like it tests nothing (and the
            # validator rightly blocks it).
            item["notes"] = (item.get("notes") or "") + \
                "; prior-year capture states the same value — fact did not change"
            print("  Same as current — recorded in notes, prior left empty.")
        else:
            item["prior_year_answer"] = value
            item["prior_source"] = {"snapshot": str(path), "quote": quote}
            print(f"  prior_year_answer = {value!r}")
        changed += 1

    if changed:
        with BENCHMARK.open("w", encoding="utf-8") as f:
            for row in rows:
                f.write(json.dumps(row, ensure_ascii=False) + "\n")
        print(f"\nSaved. Next:  python3 src/validate.py")
    return 0


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--url", help="look up a single page instead of the sheet")
    parser.add_argument("--months", type=int, default=12,
                        help="how far back to aim, in months (default 12)")
    parser.add_argument("--fill", action="store_true",
                        help="download year-old captures for annual benchmark items, "
                             "extract the prior value, and review it")
    args = parser.parse_args()

    if args.fill:
        return fill(args.months)

    if args.url:
        archived, info = find(args.url, args.months)
        print(f"{archived}   (captured {info})" if archived else f"not found: {info}")
        return 0

    rows = rows_from_sheet()
    if not rows:
        print("No rows with a filled page_url and volatility=annual yet.")
        print("Fill page_url for some annual facts first, then run this again.")
        return 0

    # One request per unique page: several facts usually come from the same URL, and
    # the Archive should not be asked the same question five times.
    seen = {}
    print(f"Looking for copies from about {args.months} months ago.\n")
    for row in rows:
        url = row["page_url"].strip()
        if url not in seen:
            seen[url] = find(url, args.months)
            time.sleep(0.5)   # be polite to a free service
        archived, info = seen[url]
        if archived:
            print(f"  {row['id']}")
            print(f"    {archived}")
            print(f"    captured {info}")
        else:
            print(f"  {row['id']}: {info}")

    found = sum(1 for v in seen.values() if v[0])
    print(f"\n{found}/{len(seen)} page(s) have an archived copy.")
    print("\nOpen each link, read the previous cycle's value, and put it in the")
    print("prior_year_answer column. If a page has no archive, leave it empty —")
    print("a missing prior value costs nothing, a guessed one corrupts the analysis.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
