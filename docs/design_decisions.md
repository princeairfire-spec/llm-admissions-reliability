# Design decisions

A dated record of choices made before data collection, and the reasoning behind each.
Written in advance so that outcomes cannot be reinterpreted after the fact.

---

## DD-001 — Claim structure: floor plus upside, not a single bet
*Decided 2026-08-07, before any data collection.*

The paper does not stake its contribution on one statistical test. Three tiers:

1. **Guaranteed.** The artifact: a public admissions-facts dataset with archived
   official-source snapshots, per-item access dates, and a reported disagreement rate
   between two independent verification passes. Plus the abstention / confident-error
   split in a domain with concrete error cost. These exist regardless of what the
   numbers say.
2. **Near-certain.** Main effects for coverage tier and volatility, framed as
   replication of PopQA (2212.10511) and MuLan (2404.03036) in a high-cost domain.
3. **Exploratory.** The coverage × volatility interaction.

**Why:** detecting an interaction of a given size requires roughly four times the
sample needed for a main effect of that size. At ~240 items over 3 tiers × 2 volatility
levels we have ~40 per cell before language and search splits, so the interaction test
is underpowered by construction. A wide confidence interval spanning zero would mean
"we could not distinguish", which is *not* the same as "the effects are additive". The
work must not depend on that test resolving.

## DD-002 — Both interaction outcomes are declared informative in advance
*Decided 2026-08-07, before any data collection.*

Pre-committed interpretations, recorded now so neither can be reverse-engineered later:

- **Additive** → coverage failure and staleness failure are independent mechanisms.
  Retrieval addresses coverage; it does not, on its own, address staleness. Different
  mitigations are required for each.
- **Super-additive** → volatile facts about low-coverage institutions form a distinct
  danger zone, and the practical warning is stronger than either main effect implies.
- **Sub-additive / floor** → low-coverage accuracy is already so low that volatility
  cannot degrade it further. Reported as a floor effect, not as evidence of no
  interaction. See DD-003.

The interaction is reported with confidence intervals, labelled exploratory, and not
converted into a headline claim whatever it shows.

## DD-003 — `prior_year_answer` field and the stale / fabricated error split
*Decided 2026-08-07, before any data collection.*

Each item records the value of the same fact for the previous admissions cycle, in a
`prior_year_answer` field, captured during verification while the official page is
already open.

Every incorrect answer is then classified as:

- **stale** — matches a previously-correct value; the model is behind, not inventing
- **fabricated** — matches no value the fact has ever held

**Why this matters more than it looks:**

1. *It survives a floor effect.* The expected failure mode for annual facts is accuracy
   collapsing toward zero across every coverage tier. If that happens, the interaction
   in DD-002 becomes unmeasurable — low-tier accuracy has nowhere left to fall. But the
   **proportion of errors that are stale rather than fabricated** remains well-defined
   and comparable across tiers even at zero accuracy. It is the analysis that still
   works when the primary one does not.
2. *It is genuinely unoccupied.* MuLan, FreshQA and AbstentionBench all treat an error
   as an error. The distinction between a model that is *out of date* and one that is
   *inventing* has different causes and different fixes, and has not been measured on
   public, snapshot-backed data in this domain.
3. It gives the Analysis section of the paper its actual content.

Cost: seconds per item during verification, since the author is already on the official
page. Cheapest high-value addition available.

## DD-004 — Metric vocabulary borrowed from MSQA
*Decided 2026-08-07.*

Use CO (correct), NA (non-committal / abstention), IN (concretely incorrect), CGA
(correctness given attempt), F (harmonic mean of CO and CGA), following MSQA
(2607.00724). No new metric names are invented.

**Why:** free comparability with a current benchmark, and the CO/NA/IN split is exactly
the abstention-versus-confident-error separation the study needs.

## DD-007 — Model-assisted extraction with mechanical checks and human acceptance
*Decided 2026-08-08, before data collection.*

Gold answers are **proposed** by a model reading an archived page and **accepted** by a
person. They are never produced from a model's memory. This section has to appear in the
paper's methods, because a reader must be able to judge the protocol rather than take
"human verified" on trust.

**Why extraction is not the fatal error.** The failure that destroys a benchmark is
using a model's *recollection* as the standard, then grading models against it — that
measures agreement between models, not agreement with reality. Extraction is a different
task: the model is shown a document and asked to copy a value and the sentence
containing it. It has no opportunity to recall, and its output is not trusted anyway.

**Three mechanical checks, before any human sees a candidate.** All are substring tests
over the archived page; no model is involved in any of them.

1. The quote must appear verbatim in the snapshot. A fabricated quote is discarded.
2. The value must appear inside the quote. This stops a real sentence being paired with
   an invented number.
3. The quote must carry at least 20 characters beyond the value. Observed in testing:
   the extractor returned `15 December, 2026` as both the value *and* the quote. A
   reviewer shown that would be confirming a value with itself. The quote has to state
   what the value *is*.

**The extractor is excluded from the evaluated models** (`gemini-3.5-flash-lite`),
so no model is graded against a standard it wrote. Recorded on every candidate.

**A check on the reviewer, redesigned after it failed.** The first version shifted a
digit in the value. That broke the machine-checked property "the value appears inside the
quote" — so the check tested the reviewer on something the pipeline already verifies, and
the interface gave no cue, because the highlighter can only mark a value that is present.
The first such check was accepted in review, and the design deserved it.

A check now substitutes a different real number from the same sentence: a credit count
offered as a duration. All three mechanical checks pass, the value is highlighted
normally, and only reading the sentence against the question catches it — which is
precisely the human contribution being measured. Only quotes with a second number can
carry a check, so they are rarer than the nominal 5%.
Two numbers go in the paper:

- **acceptance rate** — near 100% is uninformative on its own
- **control catch rate** — this is what makes "a human verified it" a measured claim

**Known limitation, to state plainly.** The extractor finds facts that are stated
plainly and misses facts stated awkwardly, so the benchmark is biased toward
clearly-worded facts — possibly the same ones models answer well, which would inflate
accuracy. Mitigation: on 3–4 pages, the author searches independently and the coverage
is compared. The difference is reported.

**Extraction is targeted, not open.** The model is given a fixed list of fields and
fills only those. Open-ended extraction would return whatever each page happens to
emphasise, and the cell balance that DD-001 depends on would collapse.

**Facts with several stated values are surfaced, not silently dropped.** The first
version instructed the extractor to omit a field when the page gave a range or
conditional values. On real pages that suppressed almost everything: Harvard's
cost-of-attendance page lists tiered tuition ($59,048 for the first two years, $15,352
afterwards, plus per-programme figures), and the extractor returned nothing at all
rather than reporting the ambiguity. Yield went from 3 candidates across 52 pages to 18
once the rule was removed.

The extractor now returns every stated value as its own candidate and a person decides
whether the fact is well defined enough to use. This is the right division: "does this
institution have a single annual tuition figure?" is a judgement about the world, not a
string-matching problem, and it should not be made silently by a model. Items where no
single value exists are excluded by a recorded human decision, which is reportable;
excluded by an extractor's silence, which is not.

**A snapshot must be checked against the URL it claims to be.** Snapshots are named
`<institution>-<level>-<role>`, which does not depend on the URL. Changing a URL in the
page list therefore left the old capture in place and silently reused it: extraction ran
against the previous page while the benchmark would have recorded the new `source_url`
beside it. Nothing failed — the quote was real, the checks passed, the item looked
sound — and the evidence chain was broken with nothing to show for it. Found only by
comparing four snapshots against the list by hand.

`extract.py fetch` now reads the URL recorded in each snapshot's metadata sidecar and
re-archives when it no longer matches, moving the superseded capture to
`data/snapshots/superseded/` rather than deleting it. The general lesson for the paper's
methods section: an archive is only evidence if something checks that it is an archive
*of the thing it is filed under*.

**Known error source: one URL serving both study levels.** If the same page is listed
for `ug` and `pg`, facts about one level are filed under the other. Observed on MBZUAI,
where the undergraduate programme page was listed for both and produced a "master's"
duration of 4 years. The checks do not catch it — the quote is genuine and the value is
in it — so `extract.py` warns before extracting, and level-specific pages should be used
wherever they exist.

**Cost:** about 10 hours end to end, against 18–20 for typing the same data by hand, and
with better provenance — quotes are machine-checked against the archive rather than
retyped by a person.

**Official pages themselves lag the cycle they describe.** On 2026-08-08 Cambridge's
MPhil page still showed `Application deadline Feb. 26, 2026` — the *previous* intake,
already past. Extraction happily returned it for a question about Fall 2027 entry. The
prompt now names the cycle and instructs the extractor to omit values tied to an earlier
one, and the reviewer is the backstop.

Worth a paragraph in Analysis rather than only a fix: the study measures how far behind
models are, and here the primary source is itself behind. A model cannot be current about
a cycle its source has not published yet, which puts a floor under measured staleness
that has nothing to do with the model.

## DD-006 — Three controls, so the study isolates rather than only measures
*Decided 2026-08-07, before data collection.*

The design as written measures accuracy across conditions but cannot separate a finding
from an instrument failure. Three controls fix that. Each is a small number of extra
items, and none requires new machinery.

**1. Negative control — is the instrument sound?**
A handful of long-stable, heavily documented facts: the city of the main campus, the
year of founding. Models should be at or near ceiling. If they are not, the problem is
the question wording or the scorer, not the model's knowledge, and every other number in
the study is suspect until it is fixed. Roughly 8 items, one or two per institution.

**2. Positive control — a ground-truth fabrication rate.**
Facts first published *after* a model's training cutoff, which that model cannot know by
construction. Any specific, confident answer there is fabrication established by the
experimental setup rather than by our judgement. This gives the hallucination measure a
reference point instead of resting entirely on the stale/fabricated classifier in
`score.py`. Requires recording each model's cutoff in the manifest and choosing items
whose publication date is known from the snapshot.

**3. Reference baseline — the ceiling of what is measurable.**
The same questions asked with the archived page text pasted into the prompt. A model
that cannot answer with the source in front of it is failing to read, not failing to
know. This bounds the study: errors in the main condition above this baseline are about
knowledge, errors at or below it are about extraction. Cheap to run — the snapshots
already exist, it is one extra prompt variant, and it needs no new data.

**Why this matters more than another twenty questions.** Controls are what turn "we
measured a difference" into "the difference is caused by what we say it is." A study of
this size cannot win on sample size; it can win on being unusually careful about what
its numbers do and do not show.

**Cost:** roughly 16 extra items for controls 1 and 2, and one extra run condition for
control 3. Well inside the free-tier budget.

## DD-005 — Volatility levels must avoid a pure floor
*Decided 2026-08-07, pending pilot confirmation.*

`annual` items must not consist solely of facts for a cycle that no model could
plausibly know. A mix is required: some facts from the current published cycle
(potentially within training data) alongside facts for the upcoming cycle. Otherwise
`annual` accuracy sits at zero uniformly and carries no information.

**To be verified in the 20-question pilot** before committing to the full sample: if
pilot accuracy on annual facts is at zero across all tiers, the volatility axis needs
re-specification before Phase 2 begins, not after.

## DD-008 — The question must ask in the unit the university publishes
*Decided 2026-08-09, after the annual cells stayed empty through two extraction rounds.*

Two questions named the unit the answer had to arrive in: "the **annual** tuition fee",
"the minimum **TOEFL iBT** score". Universities do not agree on either. MIT's registrar
publishes graduate tuition per term, KTH publishes one figure for the full programme,
Cambridge publishes per year; a large share of institutions state IELTS and no TOEFL.

The extractor is forbidden to compute, so on a page that states only a per-term figure
there is no annual figure to copy and the correct response is to return nothing. It did.
Every fee page returned nothing, which read as "these pages carry no facts" — the one
result that stops you looking.

The yield loss was the smaller problem. **Publishing convention travels with country and
with sector, and so with `coverage_tier`.** Admitting only the universities that happen
to publish in the assumed unit would have made the tier comparison partly a comparison of
publishing habits, and nothing in the analysis would have revealed it.

So the question asks for the unit instead of assuming it — "state the amount and the
period it covers", "name the test and the score" — and the unit is quoted from the page
like every other part of the answer. `$33,360 per term` and `IELTS 7.0` are answers; the
model under test has to produce the qualifier too, and gets no credit for a bare number.

**Mechanically:** the amount and the qualifier are checked separately, each as a substring
of the quote, because the page writes them either side of other words and the composed
string appears nowhere. Composition happens after the checks, so the answer is readable
without weakening what was verified.

**Widening.** Requiring both parts inside one model-supplied quote discarded 15 of 22
candidates in the first run after this change: the amount sits in one table cell and
"per term" in the next, so no single narrow quote holds both, and an extractor told to
omit what it cannot satisfy correctly omits.

Rather than relax the check, the quote is **widened from the archive**: the code locates
the quote in the snapshot and extends the span outward, up to 320 characters, until the
qualifier is inside it. Substring arithmetic over the archived bytes — the model does not
choose the wider span, and cannot use widening to reach a period belonging to a different
table. Candidates carry `quote_widened` so the effect is measurable rather than assumed.

The guarantee is therefore unchanged and worth stating precisely: **every part of the
answer appears inside the quote that was shown to the person who accepted it.**

## DD-009 — The intake is read off the page, not assumed from the calendar
*Decided 2026-08-09.*

The extraction prompt fixed the cycle at `Fall 2027` and instructed the extractor to omit
any value not tied to it. In August 2026 the pages that exist state fees for the
2026–2027 academic year, so this suppressed cycle-dependent extraction almost entirely —
the visible symptom was 18 of 23 items being `stable` facts.

Asking a question about an intake the university has not published yet is not a hard
question, it is a question with no ground truth on the source the protocol treats as
authoritative.

Each cycle-stamped candidate now carries the intake **copied from its own page**, and the
question is rendered for that intake. Question wording is derived from the quoted string
by regex, never by a model, so no unquoted text reaches the benchmark.

The intake is checked against the whole archived page rather than against the quote: on a
fee table the year is a heading above the figures, and requiring both inside one quote
made most fee pages unextractable. It is weaker locality than the value's own check, and
it is compensated by the reviewer seeing the intake and rejecting a wrong year — recorded
here so the paper states it rather than implies a stronger guarantee than it has.

## DD-010 — Level-wide facts are not programme-specific facts
*Decided 2026-08-09.*

An earlier rule told the extractor to omit anything the page stated "for the institution
in general", added after institution-level questions turned out to have no answer. It is
right for duration and language of instruction, which genuinely differ per programme. It
is wrong for tuition, deadlines, English requirements, required documents and campus
city, which universities normally set for a whole level of study — MIT's fee page never
says "Electrical Engineering and Computer Science", and under the old rule it was
therefore unusable.

Facts are now split into programme-specific and level-wide, and the prompt says which
kind it is asking for. For a level-wide fact, a value stated for all graduate applicants
applies to the named programme unless the page states a different one specifically for it.

## DD-011 — Inter-annotator agreement instead of waiting for a second pass
*Decided 2026-08-09.*

The reliability number was to come from re-reviewing a sample days later. That gap is not
a formality: asked the same question the same day, a reviewer remembers the answer, and
the number measures memory while being reported as reliability.

A second annotator needs no gap. They never saw the first decisions, so their agreement is
independent on the day it is collected — and it is the stronger claim for a dataset one
person built. `--packet` exports a shuffled sample carrying no trace of the first decision,
with controls unmarked so the second annotator's attention is measured on the same footing.

Reported as raw agreement **and** Cohen's kappa. Raw agreement flatters any dataset that
is mostly accepts, and this one is roughly 62% accepts.

The intra-annotator second pass is still planned and still needs its gap. The two measure
different things, and the paper reports whichever it has, labelled for what it is.

## DD-012 — A discovered page is fetched and tested before it enters the sheet
*Decided 2026-08-09.*

Page discovery scores candidate URLs on their wording. That is enough to find plausible
pages and not enough to find correct ones. In one pass it proposed:

- `…/exemption-from-tuition-fees` for a fee row — a waiver policy, no figures;
- `…/curriculum-information-not-found` for a programme row;
- `…/students/accommodation/prospective/ug/how-to-apply/` for an admissions row.

The third is the one that matters. It is a real page with real dates and the words "how
to apply", about applying for **a room**. Nothing downstream would have caught it: the
extractor would have found a genuine deadline, the quote would have been verbatim, all
five mechanical checks would have passed, and a reviewer skimming would have seen a real
date answering a question about deadlines.

Each proposal is now fetched and must show **both** a signature of the fact and its topic
— a currency with a figure *and* the word tuition; a date *and* an application-deadline
phrase. Regexes over the page text, in `src/qualifiers.py`, shared with the extractor and
the scorer so the three stages cannot drift apart. URLs in sections that borrow admissions
vocabulary for something else (accommodation, jobs, library, conferences) are rejected on
sight.

**What this is really protecting.** Not HTTP requests, and not even extraction quota. The
reviewer is the only unparallelisable step in the pipeline, and every junk page spends a
slot in that queue. Twenty pages were rejected in the first run under this rule.

**Known limit:** the gate tests that a page states *a* fact of the right kind, not that it
states it for the right programme or the right level. Those remain the reviewer's job, and
the level warning printed before extraction remains the only automatic signal for the
second of them.
