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
    try:
        with urllib.request.urlopen(f"{API}?{query}", timeout=TIMEOUT) as response:
            data = json.loads(response.read().decode("utf-8"))
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
        return None, f"lookup failed ({exc})"

    snapshot = (data.get("archived_snapshots") or {}).get("closest")
    if not snapshot or not snapshot.get("available"):
        return None, "no archived copy"

    stamp = snapshot.get("timestamp", "")
    pretty = f"{stamp[0:4]}-{stamp[4:6]}-{stamp[6:8]}" if len(stamp) >= 8 else stamp
    return snapshot["url"], pretty


def rows_from_sheet():
    if not SHEET.exists():
        print(f"{SHEET} not found. Create it with: python3 src/sheet.py make")
        return []
    with SHEET.open(encoding="utf-8-sig", newline="") as f:
        return [r for r in csv.DictReader(f)
                if (r.get("page_url") or "").strip() and r.get("volatility") == "annual"]


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--url", help="look up a single page instead of the sheet")
    parser.add_argument("--months", type=int, default=12,
                        help="how far back to aim, in months (default 12)")
    args = parser.parse_args()

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
