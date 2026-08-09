"""Put a known URL into data/pages.csv, after checking it carries the fact.

    python3 src/add_page.py imperial:ug:english=https://www.imperial.ac.uk/study/apply/english-language/
    python3 src/add_page.py --both imperial:english=https://...      # fills ug and pg
    python3 src/add_page.py --file urls.txt                          # one per line

Sitemap mining scores URLs on their wording, which finds plausible pages rather than
correct ones: eight attempts at Imperial's English requirements produced nothing, while
one search found the page immediately. Search is the higher-precision source, but it
needs a person or a model to read the results, so the URLs arrive from outside.

They still go through the same gate as a discovered URL — fetched, and required to show
both a signature of the fact and its topic (see qualifiers.states_fact). A URL that came
from a search is not more trustworthy than one that came from a sitemap; it is only more
likely to be right, and "likely" is not a property this dataset records anywhere.
"""

import argparse
import csv
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import re  # noqa: E402

from discover import LEVEL_MARKERS, usable  # noqa: E402
from extract import PAGES  # noqa: E402
from new_item import LEVELS, UNIVERSITIES  # noqa: E402


def wrong_level(url, level):
    """Is this URL plainly about the other level of study?

    `--both` is the convenient case and the dangerous one. Harvard's English requirement
    lives on the graduate school's site; filed against the undergraduate row it would
    produce a real quote, a real score, and the wrong requirement, with every mechanical
    check passing. Cheap to catch here, invisible later.
    """
    lowered = url.lower()
    other = "pg" if level == "ug" else "ug"
    mine = any(re.search(m, lowered) for m in LEVEL_MARKERS[level])
    theirs = any(re.search(m, lowered) for m in LEVEL_MARKERS[other])
    return theirs and not mine


def parse(spec, both):
    """`uni:level:role=url`, or `uni:role=url` with --both."""
    target, _, url = spec.partition("=")
    parts = target.split(":")
    if not url.startswith("http"):
        raise ValueError(f"no URL in {spec!r}")
    if both and len(parts) == 2:
        university, role = parts
        levels = list(LEVELS)
    elif len(parts) == 3:
        university, level, role = parts
        levels = [level]
    else:
        raise ValueError(f"expected uni:level:role=url, got {target!r}")
    if university not in UNIVERSITIES:
        raise ValueError(f"unknown university {university!r}")
    for level in levels:
        if level not in LEVELS:
            raise ValueError(f"unknown level {level!r}")
    return [(university, level, role, url) for level in levels]


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("specs", nargs="*")
    parser.add_argument("--both", action="store_true",
                        help="a spec without a level fills both ug and pg. Use only for "
                             "pages the university publishes for all applicants.")
    parser.add_argument("--file", help="read specs from a file, one per line, # for comments")
    parser.add_argument("--force", action="store_true", help="overwrite a filled row")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    specs = list(args.specs)
    if args.file:
        for line in Path(args.file).read_text(encoding="utf-8").splitlines():
            line = line.split("#", 1)[0].strip()
            if line:
                specs.append(line)
    if not specs:
        parser.error("nothing to add")

    wanted = []
    for spec in specs:
        try:
            wanted += parse(spec, args.both)
        except ValueError as exc:
            print(f"  skipped: {exc}")

    with PAGES.open(encoding="utf-8-sig", newline="") as f:
        rows = list(csv.DictReader(f))
    fields = list(rows[0].keys())
    index = {(r["university"], r["level"], r["role"]): r for r in rows}

    added = rejected = occupied = 0
    checked = {}
    for university, level, role, url in wanted:
        row = index.get((university, level, role))
        label = f"{university}-{level}-{role}"
        if row is None:
            print(f"  {label}: no such row in {PAGES}")
            continue
        if row["url"].strip() and not args.force:
            occupied += 1
            print(f"  {label}: already filled, left alone (--force to replace)")
            continue
        if wrong_level(url, level):
            rejected += 1
            print(f"  {label}: rejected — URL is about the other level of study")
            continue

        # One fetch per distinct (url, role): the same page usually serves both levels.
        key = (url, role)
        if key not in checked:
            checked[key] = usable(url, role)
        good, why = checked[key]
        if not good:
            rejected += 1
            print(f"  {label}: rejected — {why}")
            continue
        print(f"  {label}: ok  {url}")
        if not args.dry_run:
            row["url"] = url
        added += 1

    if added and not args.dry_run:
        with PAGES.open("w", encoding="utf-8-sig", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=fields)
            writer.writeheader()
            writer.writerows(rows)

    print(f"\n{added} row(s) filled, {rejected} rejected by the fact check"
          + (f", {occupied} already had a URL" if occupied else "")
          + (" (dry run, nothing written)" if args.dry_run else ""))
    if added and not args.dry_run:
        print("\nNext:  python3 src/extract.py fetch && python3 src/extract.py run")
    return 0


if __name__ == "__main__":
    sys.exit(main())
