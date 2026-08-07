"""Archive official pages so every gold answer stays checkable.

Admissions pages change every cycle. Without a snapshot, a reader in six months has no
way to tell whether a gold answer was wrong or whether the page simply moved on. The
snapshot is what turns a claim into evidence.

    python3 src/collect.py https://mbzuai.ac.ae/study/ug-admission-process/ mbzuai-ug
    python3 src/collect.py --from-benchmark data/benchmark.jsonl

Files land in data/snapshots/<slug>-<date>.html and are never overwritten: re-running on
the same day with the same slug leaves the existing file alone. An archive you can
silently overwrite is not an archive.

Standard library only — urllib is enough here, and one fewer dependency is one fewer
thing to explain in the methods section.
"""

import argparse
import json
import sys
import urllib.error
import urllib.request
from datetime import date
from pathlib import Path

SNAPSHOT_DIR = Path("data/snapshots")

# Many university sites reject requests without a browser-shaped User-Agent. This is
# an ordinary polite fetch of a public page, not evasion: identifying the project is
# the honest thing to do, and it gives an administrator someone to contact.
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0 Safari/537.36 "
        "(llm-admissions-reliability research crawler; 1 request per page)"
    ),
    "Accept": "text/html,application/xhtml+xml",
    "Accept-Language": "en-US,en;q=0.9",
}

TIMEOUT_SECONDS = 30


def snapshot_path(slug, when=None):
    """Where a snapshot for this slug, fetched today, belongs."""
    return SNAPSHOT_DIR / f"{slug}-{when or date.today().isoformat()}.html"


def fetch(url, slug):
    """Download one page and write it next to a small metadata sidecar.

    Returns the path written, or None on failure. Failures are reported and skipped
    rather than raised, so one dead link does not abort a batch of thirty.
    """
    destination = snapshot_path(slug)
    if destination.exists():
        print(f"  = {destination} already exists, leaving it alone")
        return destination

    request = urllib.request.Request(url, headers=HEADERS)
    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT_SECONDS) as response:
            body = response.read()
            final_url = response.geturl()
            status = response.status
    except urllib.error.HTTPError as exc:
        print(f"  x HTTP {exc.code} for {url}")
        return None
    except urllib.error.URLError as exc:
        print(f"  x could not reach {url}: {exc.reason}")
        return None
    except TimeoutError:
        print(f"  x timed out after {TIMEOUT_SECONDS}s: {url}")
        return None

    SNAPSHOT_DIR.mkdir(parents=True, exist_ok=True)
    destination.write_bytes(body)

    # A redirect means the saved page is not the URL recorded in the benchmark. That
    # matters when checking the item later, so record where the request actually landed.
    metadata = {
        "requested_url": url,
        "final_url": final_url,
        "http_status": status,
        "fetched_at": date.today().isoformat(),
        "bytes": len(body),
    }
    destination.with_suffix(".json").write_text(
        json.dumps(metadata, indent=2, ensure_ascii=False), encoding="utf-8"
    )

    print(f"  + {destination}  ({len(body):,} bytes)")
    if final_url != url:
        print(f"    note: redirected to {final_url}")

    # A page far smaller than a real admissions page is usually a cookie wall, a
    # JavaScript shell, or a bot-check page rather than the content.
    if len(body) < 2000:
        print("    warning: suspiciously small — open it and check it is the real page")

    return destination


def from_benchmark(path):
    """Re-archive every source_url in a benchmark file.

    Useful to re-run close to submission: a second snapshot months later documents
    exactly what changed, which is itself a result worth a line in the paper.
    """
    seen = set()
    for raw in Path(path).read_text(encoding="utf-8").splitlines():
        if not raw.strip():
            continue
        item = json.loads(raw)
        url = item.get("source_url")
        if not url or url in seen:
            continue
        seen.add(url)
        print(f"{item['id']}: {url}")
        fetch(url, item["id"])
    print(f"\n{len(seen)} unique URLs")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("url", nargs="?", help="page to archive")
    parser.add_argument("slug", nargs="?", help="short name for the file, usually the item id")
    parser.add_argument("--from-benchmark", metavar="PATH", help="re-archive every source_url in a benchmark file")
    args = parser.parse_args()

    if args.from_benchmark:
        from_benchmark(args.from_benchmark)
        return 0
    if not args.url or not args.slug:
        parser.print_help()
        return 1

    print(f"{args.slug}: {args.url}")
    return 0 if fetch(args.url, args.slug) else 1


if __name__ == "__main__":
    sys.exit(main())
