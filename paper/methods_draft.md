# §3 Benchmark construction — draft prose

Numbers in ⟨angle brackets⟩ are placeholders recomputed from the repository at
submission time. Nothing else in this section should need to change with the data.

---

## 3.1 Questions

Each item asks one factual admissions question about one named degree programme at one
institution — an application deadline, a tuition fee, a minimum English test score, a
count of required recommendation letters, an eligibility threshold, a language of
instruction, a programme duration, or a campus city. Items are stratified along two axes
fixed in advance: **coverage tier** (high / mid / low, by how prominently the
institution appears in web text) and **volatility** (annual facts, which are re-set
every admissions cycle, versus stable facts). Every question is written in English and
in Russian; the Russian wording is part of the item, not a translation layer at query
time.

Two wording rules came out of failed first versions rather than foresight, and both are
worth stating because each removes a bias.

First, a question never names the unit the answer must arrive in. An early draft asked
for "the annual tuition fee"; MIT publishes graduate tuition per term, KTH per full
programme, Cambridge per year, and a large fraction of institutions publish an IELTS
minimum and no TOEFL. Since publishing convention travels with country and sector — and
therefore with coverage tier — keeping unit-fixed questions would have quietly turned
the tier comparison into a comparison of publishing habits. Instead the question asks
for the unit alongside the value ("state the amount and the period it covers, as the
university states them"), and the unit is part of the gold answer.

Second, cycle-dependent questions name the intake that the source page actually
documents, which is read off the page itself, never assumed from the calendar. In
August 2026 the pages that exist describe the 2026–27 cycle; a question about Fall 2027
would have no ground truth on the official source, which makes it not a hard question
but an unanswerable one. The intake string is quoted from the archived page and
converted to question wording by a fixed rule, so no unquoted text reaches an item.

## 3.2 Sources

Ground truth comes only from the institutions' own pages. Every page used is archived
at collection time; the snapshot's bytes, the URL requested, and the access date are
stored in the public repository, and third-party credentials that some sites embed in
their markup are stripped at archiving time. If a page's URL is later changed in the
source sheet, the stale snapshot is moved aside rather than silently reused — an
archive is only evidence if something checks that it is an archive of the thing it is
filed under.

## 3.3 Candidate answers

Gold answers are proposed by a model reading an archived page and accepted or rejected
by a person. The model is never asked to recall anything: it is shown the page text and
asked to copy out a value and the verbatim text that states it. Extraction from a
document in view is a different task from recall, and the output is not trusted anyway.
Every candidate must pass five deterministic checks — substring tests against the
snapshot, with no model involved — before a person sees it:

1. the quote appears verbatim in the archived page;
2. the value appears inside the quote;
3. the quote carries context beyond the value itself;
4. where a value is meaningless alone (a fee without its period, a score without its
   test), the qualifier also appears inside the quote;
5. where the fact belongs to an intake, the intake string appears in the archived page.

Check 4 is made satisfiable by construction: pages put an amount in one table cell and
its period in another, so the quote is *widened* — by substring arithmetic over the
archived bytes, never by the model — until it contains the page's own wording of the
qualifier. Widening only grows the span, so checks 1–3 continue to hold on the result.
Check 5 is deliberately weaker than the others (the intake is matched against the whole
page rather than the quote, because on fee tables the year is a heading above the
figures); it scopes the question rather than answering it, and the reviewer sees the
intake alongside the candidate.

The extractor (⟨gemini-3.5-flash-lite⟩) is excluded from the models under evaluation,
so no model is graded against a standard it wrote. One bias remains and is reported
rather than fixed: an extractor finds facts that are stated plainly and misses facts
stated awkwardly, so the benchmark leans toward clearly-worded facts — plausibly the
same ones models answer well. On ⟨N⟩ pages the author searched independently and the
coverage difference is reported in §7.

## 3.4 Human review

A reviewer accepts a candidate only if the quoted text states the value *and* the value
answers the question asked. The second half is the entire human contribution: a genuine
figure from a genuine sentence can still answer a different question — a continuation
fee is not a tuition fee, a scholarship deadline is not an application deadline, and a
per-course rate next to a footnote about workload is not a fee with a period.

Whether the review actually does this job is measured, not asserted. A fraction of
candidates are attention checks: the value is replaced by a *different real number from
the same quote*, so every mechanical check passes, the interface highlights the wrong
number exactly as it would the right one, and only reading the sentence against the
question catches it. (An earlier design corrupted a digit instead; that broke a
machine-checked property, produced no visual cue, and was rightly missed — a check must
test the one thing only the person can do.) We report the catch rate — currently
⟨7/7⟩ for the first annotator, ⟨2/2⟩ for the second — alongside the acceptance rate
(⟨65.5%⟩). Deduplication bookkeeping is excluded from both rates: when the same fact is
proposed twice and one copy is removed at import, that removal is not a rejection, and
counting it as one silently rewrites the acceptance rate.

## 3.5 Reliability

Two numbers, measuring different things.

**Inter-annotator agreement.** A second person, who had not seen the dataset or any
first-pass decision, judged a shuffled sample of ⟨40⟩ candidates carrying no trace of
the first decisions, with attention checks left unmarked. Agreement is computed against
the first reviewer's judgement of the *fact* — not against a row's bookkeeping status,
which would count deduplication as disagreement. Raw agreement was ⟨84.2%⟩ with
Cohen's κ = ⟨0.599⟩; raw agreement alone flatters any dataset that is mostly accepts,
so both are reported. All ⟨6⟩ disagreements were resolved and the resolutions, with
reasons, are recorded per item in the repository.

**Intra-annotator consistency.** The first reviewer re-judges a random sample after a
gap of at least a week, blind to their earlier decisions. The gap is the instrument:
re-judging the next day measures memory and reports it as reliability. ⟨pending —
scheduled for 18 August 2026⟩.

## 3.6 Prior-cycle values

Each annual item carries, where recoverable, the value the same fact held in the
previous admissions cycle — the field that separates a model that is *out of date* from
one that is *inventing* (§5). Prior values are recovered by pointing the identical
pipeline at the Internet Archive: the capture from roughly a year before is downloaded
and stored in the repository, the same extractor proposes the prior value, the same
substring checks run against the archived bytes, and the same reviewer accepts or
rejects. Two hazards are handled mechanically. Year-stamped URLs (`…-2026-2027`) never
archive their way into the previous cycle, so the sibling URL with both years
decremented is looked up instead; and a capture younger than nine months documents the
current cycle, so it is skipped — a fabricated "value did not change" is worse than a
blank. Where no usable capture exists the field stays empty, and the item simply does
not contribute to the stale/fabricated split.
