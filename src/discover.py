"""Fill the empty rows of data/pages.csv from the universities' own page lists.

    python3 src/discover.py                    # sitemaps and archived links, then write
    python3 src/discover.py --dry-run          # show what it would add
    python3 src/discover.py --source sitemap   # one strategy only

Finding pages one search at a time is the slowest part of building this dataset. Two
cheaper sources exist.

**Links already downloaded.** An admissions page points at "Fees", "Entry requirements",
"How to apply"; a programme page points at "Structure". Those links arrived inside the
snapshots and were thrown away.

**The site's own sitemap.** Link mining only reaches pages linked from something already
archived, which is why the `english` rows stayed empty the longest: language requirements
usually sit in an applicant section no programme page links to. A sitemap lists them
however they are linked.

## Why a proposed page is fetched before it is written down

A URL that reads like a fee page is not a page with a fee on it. Scoring on wording alone
proposed `exemption-from-tuition-fees` and `curriculum-information-not-found`, and — worse,
because it looked right — an *accommodation* application page for an admissions row: it
had dates and the words "how to apply", and nothing downstream would have questioned it.

So each proposal is fetched and must show two things in its text: a signature of the fact
(a currency with a figure, a test name with a score, a date) **and** the topic (tuition,
English, an application deadline). Both are regexes over the page; no model is involved.

The cost of skipping this check is not a wasted HTTP request. It is an extraction call
and then a slot in the reviewer's queue — and the reviewer is the one part of this
pipeline that cannot be parallelised.

It proposes pages, never facts. Everything downstream is unchanged: the extractor still
reads the archived page, the mechanical checks still run, and a person still accepts or
rejects each candidate.
"""

import argparse
import csv
import gzip
import html
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from collect import HEADERS  # noqa: E402
from extract import PAGES, read_pages, slug_for  # noqa: E402
from new_item import LEVELS, UNIVERSITIES  # noqa: E402
from qualifiers import OFF_TOPIC, states_fact  # noqa: E402
from sheet import SOURCES  # noqa: E402

SNAPSHOTS = Path("data/snapshots")

# What a link has to look like to be worth checking, per page role. Matched against the
# link text and the URL together. Deliberately narrow: a wrong guess costs an HTTP
# request and a row in the sheet, but a page full of irrelevant links costs extraction
# quota, which is the scarce thing.
ROLE_HINTS = {
    "fees": ["tuition", "fees", "cost of attendance", "cost-of-attendance", "costs"],
    "english": ["english language", "english-language", "language requirement",
                "toefl", "ielts", "language proficiency"],
    "admissions": ["how to apply", "how-to-apply", "application deadline", "deadlines",
                   "entry requirement", "entry-requirement", "admission requirement",
                   "apply now", "application process", "dates and deadlines"],
    "program": ["programme structure", "program structure", "curriculum",
                "course structure", "programme overview", "study programme"],
}

# Links that match a hint but never carry the fact: news, events, logins, media.
NEVER = ["news", "/event", "login", "privacy", "cookie", "sitemap", "search?",
         "facebook", "twitter", "linkedin", "youtube", "instagram", ".pdf",
         "mailto:", "javascript:", "/alumni", "/donate", "/giving"]

TIMEOUT = 12

# Where a site advertises its own page list. Link mining can only reach pages linked from
# something already archived, which is why the `english` rows stayed empty: language
# requirements usually sit in a separate applicant section that the programme page does
# not link. A sitemap lists them regardless of how they are linked.
SITEMAP_PATHS = ["/sitemap.xml", "/sitemap_index.xml", "/sitemap-index.xml",
                 "/sitemap/sitemap.xml"]
MAX_SITEMAPS = 15          # nested sitemaps to follow per institution
MAX_URLS = 60000           # per institution, before scoring

# Words that place a URL at one level of study, used to reject a page belonging to the
# other level — a silent error, since the quote is real and every mechanical check passes
# and only the level is wrong.
# Regexes, not substrings: "graduate" is inside "undergraduate", so a plain substring
# test filed every undergraduate fee page as a postgraduate one — a silent error, since
# the page is real and the fee on it is real and only the level is wrong.
LEVEL_MARKERS = {
    # "undergrad" rather than "undergraduate": it covers both spellings, and sites shorten
    # it in paths far more often than they write it out.
    "ug": [r"undergrad", r"bachelor", r"/ug/", r"-ug-", r"freshman", r"first-year",
           r"baccalaureate"],
    # Graduate schools often identify themselves by acronym or subdomain rather than by
    # the word: Harvard's requirement lives on gsas.harvard.edu and says "graduate"
    # nowhere in the path. Every "grad" pattern carries the (?<!under) guard, because
    # "undergrad" contains "grad" the same way "undergraduate" contains "graduate".
    "pg": [r"postgraduate", r"(?<!under)graduate", r"master", r"msc", r"/pg/", r"-pg-",
           r"phd", r"doctoral", r"gsas", r"(?<!under)gradschool", r"(?<!under)grad-school",
           r"(?<!under)grad\.", r"(?<!under)grad/"],
}


def fetch_text(url):
    """Body of a URL as text, transparently un-gzipping a .xml.gz sitemap."""
    request = urllib.request.Request(url, headers=HEADERS)
    with urllib.request.urlopen(request, timeout=TIMEOUT) as response:
        raw = response.read()
    if raw[:2] == b"\x1f\x8b":
        raw = gzip.decompress(raw)
    return raw.decode("utf-8", "replace")


def sitemap_entries(domain):
    """Every URL the site advertises, following sitemap indexes one level down.

    Returns [] rather than raising: an institution without a reachable sitemap is a
    normal case, not an error, and the link-mining pass still covers it.
    """
    roots = []
    try:
        robots = fetch_text(f"https://{domain}/robots.txt")
        roots += re.findall(r"(?im)^\s*sitemap:\s*(\S+)", robots)
    except Exception:
        pass
    roots += [f"https://{domain}{path}" for path in SITEMAP_PATHS]

    seen_maps, urls = set(), []
    queue = list(dict.fromkeys(roots))
    while queue and len(seen_maps) < MAX_SITEMAPS and len(urls) < MAX_URLS:
        target = queue.pop(0)
        if target in seen_maps:
            continue
        seen_maps.add(target)
        try:
            body = fetch_text(target)
        except Exception:
            continue
        locations = [html.unescape(m) for m in re.findall(r"<loc>\s*(.*?)\s*</loc>",
                                                          body, re.I | re.S)]
        # A sitemap index lists sitemaps; a sitemap lists pages. Tell them apart by the
        # wrapper element rather than by the file name, which is not standardised.
        if re.search(r"<sitemapindex", body, re.I):
            queue += [loc for loc in locations if loc not in seen_maps]
        else:
            urls += locations
    return urls[:MAX_URLS]


def score(url, role, level):
    """How well a URL fits a wanted (role, level), or None if it does not fit at all."""
    lowered = url.lower()
    if any(bad in lowered for bad in NEVER) or OFF_TOPIC.search(lowered):
        return None
    hits = sum(1 for hint in ROLE_HINTS[role] if hint.replace(" ", "-") in lowered
               or hint in lowered)
    if not hits:
        return None

    # A URL carrying the *other* level is wrong for this row and always rejected. A URL
    # carrying no level at all is the common case, not a defect: most universities put
    # English requirements and fee tables on one page for every applicant. Requiring a
    # marker on level-sensitive roles rejected every such page — which is why the
    # `english` rows, the emptiest in the sheet, stayed empty through a sitemap pass that
    # had read fifty thousand URLs. Level is resolved downstream instead: the extraction
    # prompt names the level and tells the extractor to omit values stated for the other
    # one, and pages listed under both levels already raise a warning before extraction.
    marked = any(re.search(m, lowered) for m in LEVEL_MARKERS[level])
    other = "pg" if level == "ug" else "ug"
    if any(re.search(m, lowered) for m in LEVEL_MARKERS[other]) and not marked:
        return None

    # Shorter paths are the canonical page; deep ones are usually a single programme or a
    # news item that happens to mention fees.
    depth = urllib.parse.urlparse(lowered).path.strip("/").count("/")
    return (hits * 10) + (5 if marked else 0) - depth


def from_sitemaps(rows, have, already, per_role):
    """Propose URLs for empty rows out of each institution's advertised page list."""
    wanted = {}
    for row in rows:
        if not row["url"].strip():
            wanted.setdefault(row["university"], []).append(row)
    if not wanted:
        return {}

    proposals = {}
    for university in sorted(wanted):
        domain = SOURCES.get(university, {}).get("domain", "")
        if not domain:
            continue
        print(f"  {university} ({domain}) ... ", end="", flush=True)
        urls = sitemap_entries(domain)
        if not urls:
            print("no sitemap")
            continue
        picked = 0
        for row in wanted[university]:
            role = row["role"]
            if role not in ROLE_HINTS:
                continue
            ranked = []
            for url in urls:
                if url.rstrip("/") in already or domain not in url.lower():
                    continue
                value = score(url, role, row["level"])
                if value is not None:
                    ranked.append((value, url))
            ranked.sort(key=lambda pair: (-pair[0], len(pair[1])))
            if ranked:
                key = (row["university"], row["level"], role)
                proposals[key] = [url for _, url in ranked[:per_role]]
                picked += 1
        print(f"{len(urls)} url(s), {picked} row(s) matched")
    return proposals


def links_in(path, base_url):
    """Every absolute link in a snapshot, with its anchor text."""
    raw = path.read_text(encoding="utf-8", errors="replace")
    found = []
    for match in re.finditer(r'<a\b[^>]*href=["\']([^"\']+)["\'][^>]*>(.*?)</a>',
                             raw, re.I | re.S):
        href = html.unescape(match.group(1)).strip()
        text = html.unescape(re.sub(r"(?s)<[^>]+>", " ", match.group(2)))
        text = re.sub(r"\s+", " ", text).strip()
        if not href or href.startswith(("#", "mailto:", "javascript:")):
            continue
        found.append((urllib.parse.urljoin(base_url, href), text))
    return found


def classify(url, text, domain):
    """Which page role this link looks like, or None.

    Requires the link to stay on the institution's own domain: a fee page hosted by a
    third-party payment provider is not an official source, and the whole protocol rests
    on official sources.
    """
    host = urllib.parse.urlparse(url).netloc.lower()
    if domain not in host:
        return None
    blob = f"{text} {url}".lower()
    if any(bad in blob for bad in NEVER):
        return None
    for role, hints in ROLE_HINTS.items():
        if any(hint in blob for hint in hints):
            return role
    return None


def usable(url, role):
    """Fetch the page and say whether it both answers and carries the fact.

    A HEAD check only proved the URL resolved. That let through
    `.../exemption-from-tuition-fees` and `.../curriculum-information-not-found`: pages
    that read like fee pages and state no fee. Each one costs an extraction call and,
    far more expensively, a slot in the reviewer's queue — and the reviewer is the one
    part of this pipeline that cannot be parallelised.

    One GET here removes both costs, and the test is a regex over the page text, so
    nothing about it depends on a model.
    """
    try:
        with urllib.request.urlopen(
            urllib.request.Request(url, headers=HEADERS), timeout=TIMEOUT
        ) as response:
            if response.status != 200:
                return False, f"HTTP {response.status}"
            body = response.read(600_000)
    except urllib.error.HTTPError as exc:
        return False, f"HTTP {exc.code}"
    except Exception as exc:
        return False, str(exc)[:40]

    text = page_text_from_bytes(body)
    if len(text) < 400:
        return False, "almost no text"
    if not states_fact(role, text):
        return False, f"no {role} fact on the page"
    return True, ""


def page_text_from_bytes(body):
    raw = body.decode("utf-8", "replace")
    raw = re.sub(r"(?is)<(script|style|noscript|svg).*?</\1>", " ", raw)
    text = html.unescape(re.sub(r"(?s)<[^>]+>", " ", raw))
    return re.sub(r"\s+", " ", text).strip()


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--per-role", type=int, default=1,
                        help="how many candidate links to keep per empty row (default 1)")
    parser.add_argument("--source", choices=["links", "sitemap", "both"], default="both",
                        help="where to look: links inside archived pages, the site's own "
                             "sitemap, or both (default)")
    args = parser.parse_args()

    with PAGES.open(encoding="utf-8-sig", newline="") as f:
        rows = list(csv.DictReader(f))
    fields = list(rows[0].keys())

    have = {(r["university"], r["level"], r["role"]): r for r in rows}
    already = {r["url"].rstrip("/") for r in rows if r["url"]}

    proposals = {}

    if args.source in ("sitemap", "both"):
        print("reading sitemaps:")
        proposals.update(from_sitemaps(rows, have, already, args.per_role))
        print()

    # Read every archived page once and bucket its outgoing links by role. Link mining
    # runs second so a sitemap match, which carries an explicit level marker, wins over a
    # link whose level is only inferred from the page it was found on.
    for row in (read_pages() if args.source in ("links", "both") else []):
        snapshot = next(SNAPSHOTS.glob(f"{slug_for(row)}-*.html"), None)
        if snapshot is None:
            continue
        domain = SOURCES.get(row["university"], {}).get("domain", "")
        if not domain:
            continue
        for url, text in links_in(snapshot, row["url"]):
            role = classify(url, text, domain)
            if role is None or url.rstrip("/") in already:
                continue
            key = (row["university"], row["level"], role)
            target = have.get(key)
            if target is None or target["url"] or key in proposals:
                continue          # already filled, or already proposed from the sitemap
            proposals.setdefault(key, [])
            if url not in proposals[key]:
                proposals[key].append(url)

    print(f"{sum(len(v) for v in proposals.values())} candidate link(s) "
          f"for {len(proposals)} empty row(s)\n")

    added = rejected = 0
    for key in sorted(proposals):
        university, level, role = key
        for url in proposals[key][:args.per_role]:
            if args.dry_run:
                print(f"  {university}-{level}-{role}: {url}")
                added += 1
                continue
            print(f"  {university}-{level}-{role} ... ", end="", flush=True)
            good, why = usable(url, role)
            if good:
                have[key]["url"] = url
                already.add(url.rstrip("/"))
                added += 1
                print(f"ok  {url}")
                break        # one working page per row is enough
            rejected += 1
            print(f"{why}, trying next")

    if not args.dry_run and added:
        with PAGES.open("w", encoding="utf-8-sig", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=fields)
            writer.writeheader()
            writer.writerows(rows)

    if rejected:
        print(f"\n{rejected} proposed page(s) rejected before reaching the sheet")
    print(f"\n{added} row(s) filled" + (" (dry run, nothing written)" if args.dry_run else ""))
    if added and not args.dry_run:
        print("\nNext:  python3 src/extract.py fetch && python3 src/extract.py run")
    return 0


if __name__ == "__main__":
    sys.exit(main())
