"""Show what has been annotated and what is still missing.

    python3 src/progress.py

Reads data/benchmark.jsonl and prints a grid of institution x fact, so the next thing
to do is visible without opening the data file. Run it between sessions.

Nothing here judges quality — that is src/validate.py. This only answers "what is left".
"""

import json
import sys
from pathlib import Path

BENCHMARK = Path("data/benchmark.jsonl")

# Kept in step with src/new_item.py. Order is the order they usually appear on a page,
# which is also the order that is fastest to collect in one sitting.
FACTS = ["deadline", "tuition", "english", "documents",
         "eligibility", "language", "duration", "city"]

UNIVERSITIES = [
    ("harvard", "high"), ("mit", "high"), ("oxford", "high"), ("stanford", "high"),
    ("delft", "mid"), ("trinity", "mid"), ("kaist", "mid"), ("bologna", "mid"),
    ("mbzuai", "low"), ("nazarbayev", "low"), ("innopolis", "low"), ("indonesia", "low"),
]

TARGET_PER_CELL = 30   # per coverage_tier x volatility, from docs/design_decisions.md


def main():
    if not BENCHMARK.exists():
        print(f"{BENCHMARK} does not exist yet — nothing annotated so far.")
        print("\nStart with:")
        print("  python3 src/collect.py <url> mbzuai-pg-deadline")
        print("  python3 src/new_item.py mbzuai deadline --add")
        return 0

    items = [json.loads(l) for l in BENCHMARK.read_text(encoding="utf-8").splitlines() if l.strip()]
    if not items:
        print(f"{BENCHMARK} is empty.")
        return 0

    # An id is <university>-<level>-<fact>; index by the parts we grid on.
    done = {}
    for item in items:
        parts = item["id"].split("-")
        if len(parts) >= 3:
            done.setdefault((parts[0], parts[1]), set()).add("-".join(parts[2:]))

    levels = sorted({item["id"].split("-")[1] for item in items if len(item["id"].split("-")) >= 3}) or ["pg"]

    print(f"{len(items)} item(s) in {BENCHMARK}\n")

    for level in levels:
        print(f"level: {level}")
        header = "  " + " ".join(f"{f[:4]:>5}" for f in FACTS)
        print(f"  {'':14}{header}")
        for key, tier in UNIVERSITIES:
            marks = " ".join(f"{'  +  ' if fact in done.get((key, level), set()) else '  .  '}"
                             for fact in FACTS)
            count = len(done.get((key, level), set()))
            print(f"  {key:12} {tier:4} {marks}  {count}/{len(FACTS)}")
        print()

    print("  + recorded    . still to do\n")

    # Cell balance drives whether the interaction test is possible at all, so surface it
    # here rather than making the author run validate.py to find out.
    print("coverage_tier x volatility")
    print(f"  {'':6} {'annual':>8} {'stable':>8}")
    short = []
    for tier in ("high", "mid", "low"):
        row = []
        for volatility in ("annual", "stable"):
            n = sum(1 for i in items
                    if i.get("coverage_tier") == tier and i.get("volatility") == volatility)
            row.append(n)
            if n < TARGET_PER_CELL:
                short.append((tier, volatility, TARGET_PER_CELL - n))
        print(f"  {tier:6} {row[0]:8} {row[1]:8}")

    if short:
        print(f"\nshort of the {TARGET_PER_CELL}-per-cell target:")
        for tier, volatility, missing in short:
            print(f"  {tier}/{volatility}: {missing} more")

    verified = sum(1 for i in items if i.get("verification_round") == 2)
    print(f"\nsecond-pass verified: {verified}/{len(items)}")

    # Suggest the next sitting: the institution with the most gaps at this level.
    for level in levels:
        gaps = [(key, len(set(FACTS) - done.get((key, level), set())))
                for key, _ in UNIVERSITIES]
        gaps = [g for g in gaps if g[1] > 0]
        if gaps:
            gaps.sort(key=lambda g: -g[1])
            key, missing = gaps[0]
            todo = ",".join(f for f in FACTS if f not in done.get((key, level), set()))
            print(f"\nnext sitting ({level}): {key}, {missing} fact(s) to go")
            print(f"  python3 src/new_item.py {key} --facts {todo} --add --level {level}")
            break

    return 0


if __name__ == "__main__":
    sys.exit(main())
