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
import csv
import json
import random
import sys
from datetime import date, datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from new_item import FACTS, LEVELS, UNIVERSITIES, render_questions  # noqa: E402

CANDIDATES = Path("data/candidates.jsonl")
BENCHMARK = Path("data/benchmark.jsonl")
PACKET = Path("data/review_packet.csv")
PACKET_KEY = Path("data/review_packet_key.json")

BOLD, DIM, HL, OFF = "\033[1m", "\033[2m", "\033[7m", "\033[0m"


def load():
    if not CANDIDATES.exists():
        print(f"{CANDIDATES} not found. Run: python3 src/extract.py run")
        sys.exit(1)
    return [json.loads(l) for l in CANDIDATES.read_text(encoding="utf-8").splitlines() if l.strip()]


def save(rows):
    """Write decisions back, keeping anything that appeared on disk meanwhile.

    A review sitting holds the whole file in memory and writes it out at the end. If an
    extraction run appends new candidates during that sitting, a plain overwrite drops
    them — silently, because nothing errors and the file still looks healthy. That
    happened once and cost 22 candidates.

    Rows in memory win for ids they both have (those carry the new decisions); rows only
    on disk are kept as they are.
    """
    merged = {row["id"]: row for row in rows}
    if CANDIDATES.exists():
        for line in CANDIDATES.read_text(encoding="utf-8").splitlines():
            if line.strip():
                disk_row = json.loads(line)
                merged.setdefault(disk_row["id"], disk_row)

    with CANDIDATES.open("w", encoding="utf-8") as f:
        for row in merged.values():
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


def highlight_more(marked, value):
    """Mark a second span in text that already carries markers.

    Searches outside the existing escape sequences so the second marker cannot be planted
    inside the first one's bytes, which would print as garbage and hide both.
    """
    lowered, needle = marked.lower(), value.lower()
    start = 0
    while True:
        at = lowered.find(needle, start)
        if at < 0:
            return marked
        if "\033" not in marked[max(0, at - 4):at + len(value)]:
            return marked[:at] + HL + marked[at:at + len(value)] + OFF + marked[at + len(value):]
        start = at + 1


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
    # A cycle-stamped fact carries the intake read off its own page, so the question names
    # the year the page actually documents. Asking about a year the university has not
    # published yet has no answer anywhere, which is not a question worth grading.
    if row.get("cycle_en"):
        return render_questions(row["university"], row["level"], row["fact"],
                                row["cycle_en"], row.get("cycle_ru") or row["cycle_en"])[0]
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
        # Mark the qualifier as well as the value: for a fee the period is half the
        # answer, and an unmarked "per term" is exactly the part an eye skims past.
        marked = highlight(row["quote"], row["value"])
        if row.get("qualifier") and OFF not in row["qualifier"]:
            marked = highlight_more(marked, row["qualifier"])
        print(wrap(marked))
        print()
        answer_text = row.get("answer") or row["value"]
        print(f"  Extracted answer: {BOLD}{answer_text}{OFF}")
        if row.get("qualifier"):
            # Shown separately because it is judged separately: the amount can be right
            # while the period it is attached to is the wrong one on the page.
            print(f"  {DIM}  amount {row['value']!r} + period/test {row['qualifier']!r}, "
                  f"both quoted above{OFF}")
        if row.get("cycle_quoted"):
            print(f"  {DIM}  intake read off the page: {row['cycle_quoted']!r}{OFF}")
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

    # A candidate rejected while resolving a clash was not judged to be wrong — it was
    # the same fact proposed twice, and one copy had to go. Counting those as rejections
    # dragged the acceptance rate from 64% to 45% without the reviewer changing anything,
    # which is the rate measuring the pipeline's duplication instead of its accuracy.
    def deduplicated(row):
        passes = [v.get("pass") for v in row.get("reviews", [])]
        return passes and passes[-1] == "clash"

    reviewed = [r for r in reviewed if not deduplicated(r)]
    real = [r for r in reviewed if not r["is_control"]]
    controls = [r for r in reviewed if r["is_control"]]
    accepted = sum(1 for r in real if r["decision"] == "accept")

    deduped = sum(1 for r in rows if deduplicated(r))
    print(f"\nreviewed: {len(reviewed)}  ({len(real)} real, {len(controls)} controls)")
    if deduped:
        print(f"{DIM}  {deduped} duplicate proposal(s) removed at import — not counted "
              f"as rejections.{OFF}")
    if real:
        print(f"acceptance rate: {accepted}/{len(real)} = {accepted / len(real):.1%}")
        print(f"{DIM}  Near 100% means either a very good extractor or a reviewer not reading."
              f"\n  The control result below is what tells those apart.{OFF}")

    seconds = [(first_opinion(r, rows), [v for v in r.get("reviews", [])
                                          if v.get("pass") == "second"][-1].get("decision"))
               for r in rows
               if not r["is_control"] and any(v.get("pass") == "second"
                                              for v in r.get("reviews", []))]
    seconds = [(a, b) for a, b in seconds if a in ("accept", "reject") and b in ("accept", "reject")]
    if seconds:
        agree = sum(1 for a, b in seconds if a == b)
        n2 = len(seconds)
        po = agree / n2
        from collections import Counter as _C
        ca, cb = _C(a for a, _ in seconds), _C(b for _, b in seconds)
        pe = sum((ca[l] / n2) * (cb[l] / n2) for l in ("accept", "reject"))
        line = f"\nintra-annotator (blind re-pass): {agree}/{n2} = {po:.1%}"
        line += f", kappa {(po - pe) / (1 - pe):.3f}" if pe < 1 else ", kappa undefined"
        print(line + "   <- report this in the paper")
        print(f"{DIM}  Compared against the fact-level first opinion, so import-time "
              f"deduplication does not\n  masquerade as self-disagreement. Kappa is "
              f"depressed by the accept-heavy base rate;\n  report both numbers.{OFF}")

    if controls:
        # Controls made before the redesign broke the "value appears in the quote"
        # property, so they tested something the pipeline already checks and gave the
        # reviewer no visual cue. Pooling them with the current design would understate
        # the instrument that actually measures reading.
        current = [r for r in controls if r["value"].lower() in r["quote"].lower()]
        legacy = [r for r in controls if r not in current]
        caught = sum(1 for r in current if r["decision"] == "reject")
        if current:
            print(f"\ncontrols caught: {caught}/{len(current)} = {caught / len(current):.1%}"
                  f"   <- report this in the paper")
        if legacy:
            missed = sum(1 for r in legacy if r["decision"] == "accept")
            print(f"{DIM}  {len(legacy)} control(s) of the superseded design excluded "
                  f"({missed} accepted); see DD-007.{OFF}")
        controls = current
        if caught < len(controls):
            print(f"{DIM}  Missed controls (the value was altered, the quote was not):{OFF}")
            for row in controls:
                if row["decision"] == "accept":
                    print(f"    {row['id']}: shown {row['value']!r}, page says {row['true_value']!r}")
    else:
        print("\nno controls reviewed yet")

    # Second-pass agreement: the data-quality number the paper reports.
    #
    # Only the two review passes count. Resolving a clash between two accepted values
    # for one fact also writes to the review history, and counting that as a second
    # opinion produced a reported agreement of 0% — every clash resolution looks like a
    # reversal, because rejecting the duplicate is the whole point of it. That number
    # would have gone into the paper as "annotator agreement: 0%".
    graded = [
        [v for v in r.get("reviews", []) if v.get("pass") in ("first", "second")]
        for r in rows
    ]
    both = [(r, v) for r, v in zip(rows, graded)
            if len(v) >= 2 and any(x["pass"] == "second" for x in v)]
    if both:
        agree = sum(1 for _, v in both if v[0]["decision"] == v[-1]["decision"])
        print(f"\nsecond-pass agreement: {agree}/{len(both)} = {agree / len(both):.1%}"
              f"   <- report this too")
        for row, v in both:
            if v[0]["decision"] != v[-1]["decision"]:
                print(f"    disagreed: {row['id']}")
    else:
        print("\nno second pass yet — run it several days after the first:"
              "\n  python3 src/verify.py --second-pass 50")

    undecided = sum(1 for r in rows if not r.get("decision"))
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
    try:
        return _resolve_clashes(rows, clashes)
    except (EOFError, KeyboardInterrupt):
        # Whatever was settled before the interruption — including every clash resolved
        # automatically — is real work and belongs on disk. Losing it to a stray Ctrl-C
        # or to a non-interactive run means doing it again, and this file has already
        # cost the reviewer their decisions twice.
        save(rows)
        print("\n\nStopped. Everything decided so far has been saved.")
        print("Continue with:  python3 src/verify.py --import")
        return 0


def _resolve_clashes(rows, clashes):
    for base, group in list(clashes.items()):
        # Byte-identical proposals are the same evidence twice over, not a choice.
        # Asking about them wastes the reviewer's attention on a question with one
        # possible answer, which is how a real clash gets rubber-stamped along with them.
        # Identity that matters here is the *answer*, not the evidence. Keying on
        # (value, quote) left four of nine clashes for a person to arbitrate where every
        # proposal carried the same answer string and only the quote differed — so the
        # question put to them was "which sentence do you prefer", dressed up as "which
        # is the answer". That is worse than a wasted minute: rubber-stamping four
        # non-questions in a row is how the fifth, a real choice, gets rubber-stamped too.
        #
        # When the answers agree, keep the one with the most context around it, since the
        # quote's job from here on is to let a reader check the fact.
        answers = {(r.get("answer") or r["value"]).strip().lower() for r in group}
        if len(answers) == 1:
            group.sort(key=lambda r: len(r["quote"]), reverse=True)
            for row in group[1:]:
                row["decision"] = "reject"
                row.setdefault("reviews", []).append({
                    "pass": "clash", "decision": "reject",
                    "at": datetime.now(timezone.utc).isoformat(),
                })
            print(f"  {base}: {len(group)} proposals, all saying "
                  f"{(group[0].get('answer') or group[0]['value'])!r} — kept the "
                  f"best-evidenced one automatically.")
            continue

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

        # Three cases, not two. The question used to read "same answer in different
        # words, or a different answer?", which has no room for the commonest case on an
        # English-requirements page: TU Delft accepts "TOEFL iBT 90, or IELTS 6.5", and
        # both are correct answers to the question asked. Answering "different" there
        # would throw one away, and a model giving it would later be marked wrong for
        # quoting the university accurately.
        print("\n  The other value(s):")
        for row in others:
            print(f"    {(row.get('answer') or row['value'])!r}")
        print(f"{DIM}    w = also acceptable — the same answer reworded, or a second "
              f"answer the university\n        itself allows (a different test, a "
              f"part-time track it presents as equal)."
              f"\n    d = not acceptable — states something else, or a value this "
              f"question does not ask for.{OFF}")
        while True:
            same = input("  Are the others acceptable answers too? [w/d] ").strip().lower()
            if same in ("w", "d"):
                break

        if same == "w":
            gold.setdefault("variants", [])
            gold["variants"].extend(r.get("answer") or r["value"] for r in others)
            print(f"  Kept {gold['value']!r}; the rest recorded as acceptable answers.")
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


def make_packet(rows, size, seed):
    """Export a sample for a second person to judge independently.

    Why this exists alongside --second-pass. The second pass asks the same reviewer the
    same questions again, and it only means anything after enough days that they have
    forgotten their answers; done sooner it measures memory and reports it as reliability.
    A second *person* needs no waiting: they never saw the first decisions, so their
    agreement is independent on the day it is collected. It is also the stronger number —
    inter-annotator agreement is what a reader wants to know about a dataset one person
    built, and it is the one the paper should lead with.

    The packet carries no trace of the first decision, and controls are not marked, so the
    second annotator's catch rate is measurable on the same footing as the first's.
    """
    decided = [r for r in rows if r.get("decision")]
    if not decided:
        print("Nothing reviewed yet — there is nothing to check against.")
        return 1

    sample = random.Random(seed).sample(decided, min(size, len(decided)))
    random.Random(seed + 1).shuffle(sample)

    key = {}
    with PACKET.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["n", "question", "quote_from_official_page", "proposed_answer",
                         "correct? y/n", "note (optional)"])
        for n, row in enumerate(sample, start=1):
            key[str(n)] = row["id"]
            writer.writerow([n, question_for(row), row["quote"],
                             row.get("answer") or row["value"], "", ""])
    PACKET_KEY.write_text(json.dumps({"seed": seed, "map": key,
                                      "created": date.today().isoformat()},
                                     ensure_ascii=False, indent=1), encoding="utf-8")

    print(f"Wrote {len(sample)} item(s) to {PACKET}")
    print(f"{DIM}  The mapping back to candidate ids is in {PACKET_KEY}; do not send that "
          f"file with the packet.{OFF}")
    print("\nGive the CSV to someone who has not seen this dataset. Ask them to fill the")
    print("'correct? y/n' column: does the quoted text state that answer, for the thing")
    print("the question asks about? Tell them some items are wrong on purpose.")
    print(f"\n  open -a Numbers {PACKET}")
    print(f"\nWhen it comes back:  python3 src/verify.py --merge-packet {PACKET}")
    return 0


def fill_packet():
    """Walk the second annotator through the packet at this terminal, in Russian.

    Exists because the realistic second annotator sits at the same computer: mailing a
    CSV back and forth through a spreadsheet adds an export step where a novice loses
    the file format, and none of that friction buys any independence. Independence comes
    from two things this interface preserves: the packet rows carry no trace of the
    first decisions, and the first reviewer walks away from the keyboard.

    Russian, because the annotator this project actually has reads Russian. The quote
    stays in the page's own language — it is the evidence, and judging whether it states
    the answer needs only enough English to compare a number and a word.

    Writes into the same CSV that --merge-packet reads, so the two hand-off styles are
    interchangeable and the paper does not care which was used.
    """
    if not PACKET.exists():
        print(f"{PACKET} not found. First:  python3 src/verify.py --packet 40")
        return 1
    with PACKET.open(encoding="utf-8-sig", newline="") as f:
        rows = list(csv.DictReader(f))
    fields = list(rows[0].keys())
    answer_col = next(k for k in fields if "correct" in k)
    note_col = next(k for k in fields if "note" in k)

    todo = [r for r in rows if not (r.get(answer_col) or "").strip()]
    if not todo:
        print("Пакет уже заполнен. Дальше:  python3 src/verify.py --merge-packet "
              f"{PACKET}")
        return 0

    print(f"\n{BOLD}Проверка фактов — {len(todo)} строк(и).{OFF}")
    print("""
На каждом экране: вопрос, цитата с официальной страницы университета и
предложенный ответ. Ставьте «y», если ОБА условия выполнены:

  1. цитата действительно утверждает этот ответ — он там написан, а не додуман;
  2. ответ отвечает именно на заданный вопрос, а не на соседний.

Цитата может быть подлинной, а ответ всё равно неверным: настоящая дата,
но дедлайн стипендии, а не подачи документов. Часть строк испорчена намеренно —
их можно поймать только чтением.

Не ищите ничего в интернете и ни с кем не советуйтесь: вопрос только в том,
следует ли ответ из цитаты.

  y = верно    n = неверно    s = пропустить    q = выйти (ответы сохранятся)
""")
    input("Enter, чтобы начать... ")

    done = 0
    for row in todo:
        print("=" * 78)
        print(f"  {row.get('n', '?')} из {len(rows)}\n")
        print("  Вопрос:")
        print(wrap(row["question"]))
        print("\n  Цитата с официальной страницы:")
        print(wrap(row["quote_from_official_page"]))
        print(f"\n  Предложенный ответ:  {BOLD}{row['proposed_answer']}{OFF}\n")

        while True:
            answer = input("  Ответ верен?  [y/n/s/q] ").strip().lower()
            if answer in ("y", "n", "s", "q", "д", "н"):
                break
        if answer == "q":
            break
        if answer == "s":
            continue
        row[answer_col] = "y" if answer in ("y", "д") else "n"
        note = input("  Заметка, если есть сомнение (Enter — нет): ").strip()
        if note:
            row[note_col] = note
        done += 1

    with PACKET.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)

    left = sum(1 for r in rows if not (r.get(answer_col) or "").strip())
    print(f"\nСохранено: {done} ответ(ов) за этот заход.")
    if left:
        print(f"Осталось {left} — продолжить можно той же командой.")
    else:
        print("Всё заполнено, спасибо! Дальше хозяин проекта запускает:")
        print(f"  python3 src/verify.py --merge-packet {PACKET}")
    return 0


def kappa(pairs):
    """Cohen's kappa for two annotators over accept/reject, stdlib only.

    Raw agreement flatters a dataset where almost everything is accepted: agreeing 90% of
    the time is unimpressive if 90% of items are accepts and both parties say yes on
    reflex. Kappa subtracts the agreement expected from each annotator's own rate.
    """
    n = len(pairs)
    if not n:
        return None
    observed = sum(1 for a, b in pairs if a == b) / n
    expected = 0.0
    for label in ("accept", "reject"):
        expected += (sum(1 for a, _ in pairs if a == label) / n) * \
                    (sum(1 for _, b in pairs if b == label) / n)
    if expected >= 1.0:
        return None          # one label only: kappa is undefined, not perfect
    return (observed - expected) / (1 - expected)


def first_opinion(candidate, rows):
    """What the first reviewer thought of the *fact* on this row.

    Not the same thing as the row's final decision. Import-time deduplication marks the
    extra copies of an accepted fact as rejected, so "$67,504 (one-year program)" — the
    gold answer of the Harvard tuition item — sat in a row whose decision read reject.
    The second annotator judged it correct, because it is. Comparing his verdict against
    the bookkeeping produced eleven "disagreements" of which nine were rows where the two
    people agree about the fact and one of them was charged with the dedup's paperwork.
    Same failure class as counting dedup rejections in the acceptance rate.

    A rejected row therefore counts as agreed-with-accept when its answer is the gold
    answer, or a recorded acceptable variant, of the same fact.
    """
    if candidate.get("decision") == "accept":
        return "accept"
    base = candidate.get("base_id", candidate["id"])
    answer = " ".join((candidate.get("answer") or candidate["value"]).split()).lower()
    for row in rows:
        if row.get("base_id", row["id"]) != base or row.get("decision") != "accept":
            continue
        accepted = [row.get("answer") or row["value"], *row.get("variants", [])]
        if answer in (" ".join(a.split()).lower() for a in accepted):
            return "accept"
    return "reject"


def merge_packet(rows, path):
    """Read a returned packet and report agreement between the two annotators."""
    if not PACKET_KEY.exists():
        print(f"{PACKET_KEY} not found — that file maps packet rows back to candidates.")
        return 1
    mapping = json.loads(PACKET_KEY.read_text(encoding="utf-8"))["map"]
    by_id = {r["id"]: r for r in rows}

    pairs, controls_caught, controls_total, blank = [], 0, 0, 0
    with Path(path).open(encoding="utf-8-sig", newline="") as f:
        for record in csv.DictReader(f):
            answer = (record.get("correct? y/n") or "").strip().lower()
            candidate = by_id.get(mapping.get((record.get("n") or "").strip(), ""))
            if candidate is None:
                continue
            if answer not in ("y", "n", "yes", "no"):
                blank += 1
                continue
            second = "accept" if answer.startswith("y") else "reject"
            # Re-merging the same packet replaces the earlier entries instead of stacking
            # a second copy — running this twice must not manufacture data.
            candidate["reviews"] = [v for v in candidate.get("reviews", [])
                                    if v.get("pass") != "second_annotator"]
            candidate["reviews"].append({
                "pass": "second_annotator", "decision": second,
                "at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            })
            if candidate["is_control"]:
                controls_total += 1
                controls_caught += second == "reject"
                continue        # controls measure attention, not agreement about facts
            pairs.append((first_opinion(candidate, rows), second))

    save(rows)
    print(f"\n{len(pairs)} item(s) judged by both people"
          + (f", {blank} left blank" if blank else ""))
    if pairs:
        agreed = sum(1 for a, b in pairs if a == b)
        print(f"raw agreement: {agreed}/{len(pairs)} = {agreed / len(pairs):.1%}")
        k = kappa(pairs)
        print(f"Cohen's kappa: {k:.3f}" if k is not None
              else "Cohen's kappa: undefined — one annotator used a single label")
        print(f"{DIM}  Report both. Raw agreement alone looks good on any dataset that is "
              f"mostly accepts.{OFF}")
        disagreements = [(a, b) for a, b in pairs if a != b]
        if disagreements:
            print(f"\n{len(disagreements)} disagreement(s) — resolve them before the "
                  f"dataset is final:\n  python3 src/verify.py --disputed")
    if controls_total:
        print(f"\nsecond annotator caught {controls_caught}/{controls_total} control(s)")
    return 0


def show_disputed(rows):
    """List items the two annotators judged differently."""
    disputed = []
    for row in rows:
        second = [v for v in row.get("reviews", []) if v.get("pass") == "second_annotator"]
        if any(v.get("pass") == "resolution" for v in row.get("reviews", [])):
            continue        # already argued out; the entry records who kept what and why
        if second and second[-1]["decision"] != first_opinion(row, rows):
            disputed.append((row, second[-1]["decision"]))
    if not disputed:
        print("No disagreements between the two annotators.")
        return 0
    print(f"{len(disputed)} item(s) judged differently:\n")
    for row, second in disputed:
        print("=" * 78)
        print(f"  {BOLD}{row['id']}{OFF}   you: {first_opinion(row, rows)}   them: {second}")
        print(wrap(question_for(row)))
        print(wrap(highlight(row["quote"], row["value"])))
        print(f"  answer: {BOLD}{row.get('answer') or row['value']}{OFF}\n")
    print(f"{DIM}Change your own decision on any of these with:  "
          f"python3 src/verify.py --revise <ID>{OFF}")
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

    # Skip anything already in the benchmark under either identity: the fact key
    # (institution-level-fact, catching alternative wordings imported across sessions)
    # or the rendered question itself. The second is the one that actually defines an
    # item — and it is weaker than the first in exactly one way: a question that names
    # no level, like the campus city, renders identically for ug and pg, so two fact
    # keys produced one question twice and the dataset failed validation.
    already, asked = {}, {}
    if BENCHMARK.exists():
        for line in BENCHMARK.read_text(encoding="utf-8").splitlines():
            if line.strip():
                item = json.loads(line)
                already[item["id"].rsplit("-alt", 1)[0]] = item["id"]
                asked[" ".join(item["question_en"].split()).lower()] = item["id"]

    added = 0
    blocked = []
    with BENCHMARK.open("a", encoding="utf-8") as out:
        for row in accepted:
            fact_key = row.get("base_id", row["id"])
            if fact_key in already:
                if already[fact_key] != row["id"]:
                    blocked.append((row["id"], already[fact_key]))
                continue
            name, country, tier = UNIVERSITIES[row["university"]]
            fact_type, volatility, _, _ = FACTS[row["fact"]]
            if row.get("cycle_en"):
                q_en_text, q_ru_text = render_questions(
                    row["university"], row["level"], row["fact"],
                    row["cycle_en"], row.get("cycle_ru") or row["cycle_en"])
            else:
                q_en_text, q_ru_text = render_questions(row["university"], row["level"],
                                                        row["fact"])

            question_key = " ".join(q_en_text.split()).lower()
            if question_key in asked:
                blocked.append((row["id"], asked[question_key]))
                continue
            asked[question_key] = row["id"]

            out.write(json.dumps({
                "id": row["id"],
                "university": name,
                "country": country,
                "coverage_tier": tier,
                "question_en": q_en_text,
                "question_ru": q_ru_text,
                "fact_type": fact_type,
                "volatility": volatility,
                "gold_answer": row.get("answer") or row["value"],
                "answer_parts": ({"amount": row["value"], "qualifier": row["qualifier"]}
                                 if row.get("qualifier") else None),
                "cycle_quoted": row.get("cycle_quoted") or None,
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
    if blocked:
        print(f"\n{len(blocked)} accepted candidate(s) describe a fact already in the "
              f"benchmark and were not added:")
        for new_id, existing in blocked:
            print(f"  {new_id}  ->  already covered by {existing}")
        print(f"{DIM}  To swap one in, delete the existing line from the benchmark and "
              f"re-run.{OFF}")
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
    parser.add_argument("--packet", type=int, metavar="N", nargs="?", const=50,
                        help="export N items for a second person to judge (default 50)")
    parser.add_argument("--packet-seed", type=int, default=20260809)
    parser.add_argument("--merge-packet", metavar="CSV",
                        help="read a returned packet and report agreement")
    parser.add_argument("--fill-packet", action="store_true",
                        help="fill the packet interactively at this terminal (Russian; "
                             "for a second annotator at the same computer)")
    parser.add_argument("--disputed", action="store_true",
                        help="show items the two annotators judged differently")
    args = parser.parse_args()

    if args.do_import:
        return import_accepted()

    if args.packet:
        return make_packet(load(), args.packet, args.packet_seed)

    if args.fill_packet:
        return fill_packet()

    if args.merge_packet:
        return merge_packet(load(), args.merge_packet)

    if args.disputed:
        return show_disputed(load())

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
