"""Review extracted candidates: accept or reject each against its quote.

    python3 src/verify.py                 # review everything undecided
    python3 src/verify.py --limit 40      # a shorter sitting
    python3 src/verify.py --stats         # acceptance rate and control results
    python3 src/verify.py --second-pass 50  # re-review a random sample, days later
    python3 src/verify.py --import        # accepted candidates -> data/benchmark.jsonl

Each screen shows the sentence taken from the archived page with the extracted value
highlighted inside it. The judgement is: does that sentence actually state that value,
for the thing the question asks about? Roughly fifteen seconds per candidate.

Some candidates are attention checks: the quote is genuine and the value is genuinely
in it, but it is the wrong number for the question — a credit count offered as a
duration, say. Every mechanical check passes, so only reading catches it. Accepting one
means the review was not doing the one job a machine cannot do, and the rate is
reported. It is a check on the process, not a trap.

`--second-pass` is the disagreement measure the paper reports. Run it several days after
the first pass, on a random sample, without looking at the earlier decisions.
"""

import argparse
import json
import random
import sys
from datetime import date, datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from new_item import FACTS, LEVELS, UNIVERSITIES, render_questions  # noqa: E402

CANDIDATES = Path("data/candidates.jsonl")
BENCHMARK = Path("data/benchmark.jsonl")

BOLD, DIM, HL, OFF = "\033[1m", "\033[2m", "\033[7m", "\033[0m"


def load():
    if not CANDIDATES.exists():
        print(f"{CANDIDATES} not found. Run: python3 src/extract.py run")
        sys.exit(1)
    return [json.loads(l) for l in CANDIDATES.read_text(encoding="utf-8").splitlines() if l.strip()]


def save(rows):
    with CANDIDATES.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")


def highlight(quote, value):
    """Show the quote with the value marked, so the eye lands on what is being judged.

    When the value is absent from the quote the marker cannot be drawn, and silently
    returning the plain quote makes the most important case the least visible — that is
    how a corrupted control got accepted during testing. Say so instead.
    """
    lowered, needle = quote.lower(), value.lower()
    at = lowered.find(needle)
    if at < 0:
        return quote + f"\n{BOLD}    [the extracted value does not appear in this sentence]{OFF}"
    return quote[:at] + HL + quote[at:at + len(value)] + OFF + quote[at + len(value):]


def wrap(text, width=76, indent="    "):
    words, lines, line = text.split(), [], ""
    for word in words:
        if len(line) + len(word) + 1 > width:
            lines.append(line)
            line = word
        else:
            line = f"{line} {word}".strip()
    lines.append(line)
    return "\n".join(indent + l for l in lines)


def question_for(row):
    return render_questions(row["university"], row["level"], row["fact"])[0]


def review(rows, targets, pass_name):
    """Walk the reviewer through a list of candidates. Returns how many were decided."""
    print(f"\n{len(targets)} candidate(s) to review.")
    print(f"{DIM}  Accept only if BOTH hold:")
    print("    1. the sentence really states this value, and")
    print("    2. this value answers the question shown above it.")
    print("  A real figure from a real sentence can still be the wrong figure —")
    print("  a continuation fee is not an annual tuition fee.")
    print(f"\n  y = accept    n = reject    s = skip for now    q = stop and save{OFF}\n")

    decided = 0
    for index, row in enumerate(targets, start=1):
        print("=" * 78)
        print(f"  {index}/{len(targets)}   {BOLD}{row['id']}{OFF}   {DIM}{row['fact']}{OFF}")
        print()
        print(f"  Question asked of the models:")
        print(wrap(question_for(row)))
        print()
        print(f"  Sentence from the archived page:")
        print(wrap(highlight(row["quote"], row["value"])))
        print()
        print(f"  Extracted value:  {BOLD}{row['value']}{OFF}")
        for reason in row.get("suspicions", []):
            print(f"  {BOLD}! probably wrong: {reason}{OFF}")
        print(f"  {DIM}{row['source_url']}{OFF}")
        print()

        # Two things have to hold, and only the first was already checked by machine.
        # Asking only "does the sentence state this value" invites accepting a real
        # quote that answers a different question — Harvard's continuation fee is a
        # genuine figure in a genuine sentence, and not the annual tuition asked about.
        while True:
            answer = input("  Is this the correct answer to the question above?  [y/n/s/q] ").strip().lower()
            if answer in ("y", "n", "s", "q"):
                break

        if answer == "q":
            break
        if answer == "s":
            continue

        row.setdefault("reviews", []).append({
            "pass": pass_name,
            "decision": "accept" if answer == "y" else "reject",
            "at": datetime.now(timezone.utc).isoformat(),
        })
        if pass_name == "first":
            row["decision"] = "accept" if answer == "y" else "reject"
        decided += 1

    return decided


def stats(rows):
    reviewed = [r for r in rows if r.get("decision")]
    if not reviewed:
        print("Nothing reviewed yet.")
        return 0

    real = [r for r in reviewed if not r["is_control"]]
    controls = [r for r in reviewed if r["is_control"]]
    accepted = sum(1 for r in real if r["decision"] == "accept")

    print(f"\nreviewed: {len(reviewed)}  ({len(real)} real, {len(controls)} controls)")
    if real:
        print(f"acceptance rate: {accepted}/{len(real)} = {accepted / len(real):.1%}")
        print(f"{DIM}  Near 100% means either a very good extractor or a reviewer not reading."
              f"\n  The control result below is what tells those apart.{OFF}")

    if controls:
        caught = sum(1 for r in controls if r["decision"] == "reject")
        print(f"\ncontrols caught: {caught}/{len(controls)} = {caught / len(controls):.1%}"
              f"   <- report this in the paper")
        if caught < len(controls):
            print(f"{DIM}  Missed controls (the value was altered, the quote was not):{OFF}")
            for row in controls:
                if row["decision"] == "accept":
                    print(f"    {row['id']}: shown {row['value']!r}, page says {row['true_value']!r}")
    else:
        print("\nno controls reviewed yet")

    # Second-pass agreement: the data-quality number the paper reports.
    both = [r for r in rows if len(r.get("reviews", [])) >= 2]
    if both:
        agree = sum(1 for r in both
                    if r["reviews"][0]["decision"] == r["reviews"][-1]["decision"])
        print(f"\nsecond-pass agreement: {agree}/{len(both)} = {agree / len(both):.1%}"
              f"   <- report this too")
        for row in both:
            if row["reviews"][0]["decision"] != row["reviews"][-1]["decision"]:
                print(f"    disagreed: {row['id']}")

    undecided = len(rows) - len(reviewed)
    if undecided:
        print(f"\n{undecided} candidate(s) still undecided")
    return 0


def resolve_clashes(rows, clashes):
    """Ask which of several accepted values is the gold answer, and what the rest are.

    Two candidates for one fact usually means the page stated it twice — the same answer
    in different words. Those belong in `acceptable_variants`, where the scorer will
    treat a model that says "one-year" the same as one that says "1 year". Occasionally
    they are genuinely different facts (NUS states 1.5 years full-time and 2.5 part-time)
    and only one can be the standard.

    Rejecting the extras outright would be wrong for the first case and losing the
    variants would quietly cost accuracy at scoring time, so the distinction is worth
    one question each.
    """
    for base, group in clashes.items():
        print("=" * 78)
        print(f"  {BOLD}{question_for(group[0])}{OFF}\n")
        for index, row in enumerate(group, start=1):
            print(f"  {index}. {row['value']!r}")
            print(f"     {DIM}{row['quote'][:90]}{OFF}")
        print()

        while True:
            choice = input(f"  Which is the answer? [1-{len(group)}, or s to skip this fact] ").strip().lower()
            if choice == "s":
                break
            if choice.isdigit() and 1 <= int(choice) <= len(group):
                break
        if choice == "s":
            continue

        gold = group[int(choice) - 1]
        others = [r for r in group if r is not gold]

        print("\n  The other value(s):")
        for row in others:
            print(f"    {row['value']!r}")
        while True:
            same = input("  Same answer in different words, or a different answer? [w/d] ").strip().lower()
            if same in ("w", "d"):
                break

        if same == "w":
            gold.setdefault("variants", [])
            gold["variants"].extend(r["value"] for r in others)
            print(f"  Kept {gold['value']!r}; the rest recorded as alternative wordings.")
        else:
            print(f"  Kept {gold['value']!r}; the rest rejected.")
        for row in others:
            row["decision"] = "reject"
            row.setdefault("reviews", []).append({
                "pass": "clash", "decision": "reject",
                "at": datetime.now(timezone.utc).isoformat(),
            })
        print()

    save(rows)
    print("Saved. Run the import again:  python3 src/verify.py --import")
    return 0


def import_accepted():
    """Turn accepted candidates into benchmark items."""
    rows = load()
    accepted = [r for r in rows if r.get("decision") == "accept" and not r["is_control"]]
    if not accepted:
        print("No accepted candidates yet.")
        return 1

    # Several candidates can describe the same fact — a page listing full-time and
    # part-time durations produces one each. They render the *same* question, so
    # accepting more than one would put a single question in the benchmark twice with
    # contradictory gold answers, and a model could not be right about both.
    by_fact = {}
    for row in accepted:
        by_fact.setdefault(row.get("base_id", row["id"]), []).append(row)
    clashes = {k: v for k, v in by_fact.items() if len(v) > 1}
    if clashes:
        print(f"{len(clashes)} fact(s) have more than one accepted value.\n")
        print("Most of these are the same answer written twice — a page saying 'English'")
        print("in two sentences, or '1 year' and 'one-year'. Those become alternative")
        print("wordings, not a problem. A few are genuinely different answers, and there")
        print("only one can be the gold answer.\n")
        return resolve_clashes(rows, clashes)

    already = set()
    if BENCHMARK.exists():
        for line in BENCHMARK.read_text(encoding="utf-8").splitlines():
            if line.strip():
                already.add(json.loads(line)["id"])

    added = 0
    with BENCHMARK.open("a", encoding="utf-8") as out:
        for row in accepted:
            if row["id"] in already:
                continue
            name, country, tier = UNIVERSITIES[row["university"]]
            fact_type, volatility, _, _ = FACTS[row["fact"]]
            q_en_text, q_ru_text = render_questions(row["university"], row["level"], row["fact"])

            out.write(json.dumps({
                "id": row["id"],
                "university": name,
                "country": country,
                "coverage_tier": tier,
                "question_en": q_en_text,
                "question_ru": q_ru_text,
                "fact_type": fact_type,
                "volatility": volatility,
                "gold_answer": row["value"],
                "acceptable_variants": row.get("variants", []),
                "prior_year_answer": None,
                "source_url": row["source_url"],
                "source_quote": row["quote"],
                "snapshot_path": row["snapshot_path"],
                "date_accessed": row.get("extracted_at", date.today().isoformat()),
                "verified_by": "author",
                "verification_round": 1,
                "round1_gold_answer": None,
                # The provenance the paper has to describe: proposed by a model from an
                # archived page, checked mechanically, accepted by a person.
                "notes": f"extracted by {row['extractor']}, accepted on review",
            }, ensure_ascii=False) + "\n")
            added += 1

    print(f"Imported {added} item(s) into {BENCHMARK}.")
    print("\nStill to do by hand:")
    print("  prior_year_answer  ->  python3 src/wayback.py")
    print("Then:  python3 src/validate.py && python3 src/progress.py")
    return 0


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--limit", type=int, help="review at most this many")
    parser.add_argument("--stats", action="store_true", help="report the review numbers")
    parser.add_argument("--second-pass", type=int, metavar="N",
                        help="re-review N random already-decided candidates")
    parser.add_argument("--import", dest="do_import", action="store_true",
                        help="write accepted candidates into the benchmark")
    parser.add_argument("--revise", metavar="ID",
                        help="re-decide one candidate by id, after a mistake or a clash")
    args = parser.parse_args()

    if args.do_import:
        return import_accepted()

    if args.revise:
        rows = load()
        target = next((r for r in rows if r["id"] == args.revise), None)
        if target is None:
            print(f"No candidate with id {args.revise!r}.")
            return 1
        was = target.get("decision")
        print(f"\nCurrent decision: {was or 'none'}")
        # The revised decision replaces the first-pass one and is appended to the review
        # history, so the second-pass agreement number still sees what changed and why.
        review(rows, [target], "first")
        save(rows)
        print(f"\n{args.revise}: {was or 'none'} -> {target.get('decision')}")
        return 0

    rows = load()
    if args.stats:
        return stats(rows)

    if args.second_pass:
        pool = [r for r in rows if r.get("decision") and not r["is_control"]]
        if not pool:
            print("Nothing decided yet to re-review.")
            return 1
        rng = random.Random()
        targets = rng.sample(pool, min(args.second_pass, len(pool)))
        print(f"\nSecond pass. Judge each one afresh — earlier decisions are not shown.")
        decided = review(rows, targets, "second")
    else:
        targets = [r for r in rows if not r.get("decision")]
        if args.limit:
            targets = targets[:args.limit]
        if not targets:
            print("Everything has been reviewed. Next: python3 src/verify.py --import")
            return 0
        decided = review(rows, targets, "first")

    save(rows)
    print(f"\nSaved. {decided} decision(s) this sitting.")
    stats(rows)
    return 0


if __name__ == "__main__":
    sys.exit(main())
