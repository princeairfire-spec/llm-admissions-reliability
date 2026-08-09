# Phase 0 — Novelty check

Date of search: 2026-08-07. Searched: arXiv, ACL Anthology, Google Scholar, general web.
Queries used are logged at the bottom of this file so the search can be reproduced and
re-run closer to submission.

**Bottom line: the project is viable, but two of the five hypotheses are no longer
novel on their own and must be reframed as replication-in-a-new-domain rather than
as contributions. The contribution has to sit in the *interaction* of the axes and in
the *public, snapshot-backed* nature of the dataset.**

---

## 1. Nearest neighbours

Ordered by how close they are to what we want to do.

### Tier A — same domain, direct competitors

**A1. Domain-Grounded Evaluation of LLMs in International Student Knowledge**
(Daitx & Amar, arXiv:2511.20653, Oct 2025)
The closest existing work. Evaluates LLMs on study-abroad questions — admissions,
visas, scholarships, eligibility — scoring accuracy and hallucination patterns, using
a HealthBench-like protocol and a shared system prompt across models.

*Why it does not close our question:* the dataset is **internal to ApplyBoard and not
released**; the paper does not disclose its size, its construction protocol, or any
annotation-agreement measure. It has **no volatility axis, no language axis, no
coverage/popularity tier, and no search-on/off condition**, and it does not separate
abstention from error. It establishes that the domain matters; it does not answer
*where and why* models fail in it, and nothing in it is independently checkable.

**A2. ImmigrationQA: A Source-Grounded Dataset and Small-Model Adaptation for U.S.
Immigration Law** (arXiv:2605.30589, May 2026)
17,058 QA pairs over 11 official sources (USCIS Policy Manual, 8 CFR, BIA decisions).
Adjacent high-stakes bureaucratic domain. Reports that general-purpose models
"routinely confus[e] similar-sounding form numbers, misstat[e] deadlines, and conflat[e]
procedural requirements."

*Relevance:* strong independent motivation for our framing — deadlines are named as a
specific failure mode. Notably, the authors flag that **47.6% of their pairs are
time-dependent** and treat this as a *limitation*, not as a variable to study. English
only; no abstention/hallucination separation; no retrieval condition; evaluation on only
101 held-out examples. This is a gap we can walk straight into.

**A3. The CitizenQuery Benchmark** (arXiv:2602.04064, Feb 2026)
Citizen–government query tasks. Same "high-stakes bureaucratic facts" motivation, a
different vertical. No volatility stratification, no education coverage.

### Tier B — the axes we want, in other domains

**B1. MuLan: A Study of Fact Mutability in Language Models** (arXiv:2404.03036)
**This is the paper that pre-empts H2 as a standalone claim.** It shows models are
better at immutable than mutable facts, and are measurably more confident on immutable
ones. Our H2 ("volatile facts are harder") is therefore *already known in general* and
must be cited as established, not presented as our finding.
*What is still open:* MuLan works over Wikidata relations, not over real
consequence-bearing facts, and does not cross mutability with entity coverage or
language.

**B2. FreshLLMs / FreshQA** (arXiv:2310.03214, Findings of ACL 2024)
The canonical fast-changing-facts benchmark: never-changing / slow-changing /
fast-changing / false-premise, plus search augmentation (FreshPrompt), plus a two-mode
(relaxed/strict) evaluation that separately captures hallucination.
*Our H2 and H5 are structurally a FreshQA-style design.* We must say so explicitly. Our
difference is domain specificity, an actual cost model for the error, and the coverage
and language axes FreshQA does not have.

**B3. When Not to Trust Language Models (PopQA)** (arXiv:2212.10511, ACL 2023)
14k questions stratified by entity popularity. Accuracy collapses on the long tail
(~19% on the 4k least-popular), and retrieval helps most exactly there.
**This pre-empts H1 as a standalone claim** in the same way MuLan pre-empts H2. Our
`coverage_tier` is PopQA's popularity axis, applied to institutions instead of Wikidata
entities.

**B4. AbstentionBench** (arXiv:2506.09038, NeurIPS 2025)
20 datasets, abstention as a first-class object; finds abstention unsolved and not
fixed by scale. Gives us the vocabulary and the metric framing for H4 — and means H4
must be phrased as "does the known abstention failure persist where the error is
costly?", not as a discovery.

**B5. MSQA** (arXiv:2607.00724, Jul 2026)
1,064 natively-sourced questions, 11 language groups. Crucially it already reports the
exact metric split we want: CO (correct), **NA (non-committal)**, **IN (concretely
wrong)**, CGA (correctness given attempt), F (harmonic mean).
**We should adopt this metric vocabulary rather than invent our own** — it makes our
numbers comparable to a current benchmark and costs us nothing. Also relevant to H3:
finds a "Locality Effect", cultural/factual competence tracking pre-training exposure.

**B6. Better To Ask in English? Evaluating Factual Accuracy of Multilingual LLMs in
English and Low-Resource Languages** (arXiv:2504.20022)
Direct precedent for H3 — a factuality gap between low- and high-resource languages
across 19 languages. Russian is comparatively well-resourced, so **our H3 is a weaker
version of an established effect** and should be framed as a secondary question.

**B7. When Benchmarks Age: Temporal Misalignment through LLM Factuality Evaluation**
(arXiv:2510.07238)
24–64% of time-sensitive samples in existing benchmarks are already stale, which
mislabels correct model answers. This is a **methodological threat to us**, not just
related work: it is the argument for dated snapshots and a stated measurement date, and
it belongs in our Limitations.

### Tier C — background, cite briefly
HalluLens (2504.17550), HaluEval, TruthfulQA, FactBench (2410.22257), FACTS Grounding
(2501.03200), the factuality survey (2310.07521).

---

## 2. Where our niche actually is

Honest statement of the situation. Each of our five hypotheses, taken alone, is either
already established (H1 by PopQA, H2 by MuLan, H3 by arXiv:2504.20022, H4 by
AbstentionBench) or is a known design pattern (H5 by FreshQA). **No single hypothesis
in the brief is, by itself, a publishable contribution in 2026.** Anyone who tells the
author otherwise is not reading the literature.

What is genuinely unoccupied is the conjunction:

1. **The interaction, not the main effects.** Everyone has measured coverage and
   mutability *separately*. Nobody has asked whether they *compound* — whether a
   volatile fact about a low-coverage university is worse than the two effects
   predict independently. That is a 2×2 (at minimum) with an interaction term, and it
   is a real empirical question with a real answer we do not know in advance. This is
   the paper's spine.

2. **Error cost is concrete and asymmetric here.** In PopQA, a wrong answer about a
   long-tail entity costs nothing. Here, a hallucinated deadline costs an application
   year. The domain is what turns an abstract calibration finding into a
   consequence-bearing one, and it licenses the "abstention is the correct behaviour"
   framing that AbstentionBench argues for abstractly.

3. **A public, snapshot-backed, independently checkable artifact.** A2 is
   source-grounded but English-only and legal-domain. A1 is our domain but its data is
   private and unspecified. **There is currently no public admissions-facts dataset with
   archived official-source evidence, a dated measurement point, and a reported
   second-pass agreement number.** That artifact is defensible on its own merits even
   if every effect we measure turns out to be one already reported elsewhere — which is
   also our insurance against the "boring results" risk in the brief.

4. **Institutions are a better-controlled coverage axis than Wikidata entities.**
   Universities are directly comparable objects — they all have a deadline, a tuition
   figure, a location, a program length. We can hold `fact_type` fixed while varying
   coverage tier, which PopQA's heterogeneous relations cannot do cleanly.

### Consequences for the design — act on these before Phase 2

- **Reframe, in the paper and in the author's head.** H1–H4 are *replications* whose
  value is that they hold in a costly domain; the *contribution* is the interaction
  (point 1) plus the artifact (point 3). Write the Introduction this way from the start.
- **Adopt MSQA's metric names** (CO / NA / IN / CGA / F). Do not invent new ones.
- **The design must support an interaction test.** This raises the priority of cell
  balance from "good practice" to "the paper does not exist without it": every
  coverage_tier must contain both volatile and stable facts, in comparable numbers.
  With ~240 items over tier(3) × volatility(2) that is ~40 per cell before the language
  and search splits — thin but workable for the interaction, and this is exactly why
  the brief's ban on shrinking the question count must hold.
- **Promote H3 (language) to a secondary question.** Russian is not low-resource; the
  expected effect is small and we may well find nothing. Report it honestly either way.
- **Record and publish the measurement date prominently** (arXiv:2510.07238). Our
  numbers are a photograph of August–October 2026, and the paper must say so.

### Fallback if a competitor appears before submission
Re-run these queries in late September 2026. If someone publishes exactly this, the
retreat position is the one the brief already names: narrow to volatile facts only and
lean on the artifact and the error typology, which are the parts nobody can scoop by
publishing a similar table.

---

## 3. Reproducible search log

Run again before submission and append results with dates.

```
LLM benchmark factual accuracy university admissions questions hallucination
arXiv temporal knowledge staleness LLM benchmark time-sensitive facts deadlines
arXiv multilingual factual QA long-tail entity coverage low-resource LLM accuracy
LLM abstention calibration high-stakes factual QA refuse to answer benchmark
"higher education" LLM chatbot accuracy admissions information students evaluation study 2026
FreshQA fast-changing facts benchmark LLM search augmentation follow-up
arXiv benchmark LLM university website factual questions tuition deadlines requirements
LLM overconfidence wrong answers volatile facts vs stable facts benchmark entity popularity
benchmark LLM immigration visa government deadlines factual accuracy high-stakes bureaucratic questions arXiv
arXiv 2026 education domain factuality benchmark study abroad international students LLM misinformation
PopQA entity popularity long-tail factual knowledge memorization retrieval benchmark
benchmark stratified by fact volatility mutable immutable facts LLM accuracy interaction entity frequency
MSQA natively sourced multilingual multicultural SimpleQA benchmark abstention
```

### Not yet done — remaining Phase 0 work for the author
- Read A1 (2511.20653), B1 (MuLan), B2 (FreshQA), B3 (PopQA), B5 (MSQA) in full. These
  five are the ones that will come up in an interview.
- Check ACL Anthology and the ACL/EMNLP 2026 proceedings directly; the searches above
  were web-weighted and may under-cover venue-only papers.
- Confirm A1's dataset really is unreleased (check for a repo or a later version).

---

## 4. Phase 0 addendum — second search, 2026-08-09

Four papers surfaced in a follow-up search; all four verified against arXiv abstracts
on 2026-08-09. Three are from 2026 and postdate the first search. This is what Phase 0
re-runs are for: finding these now is a working note, finding them in a review is a
rejection.

**A4. MARAUS: Multi-Agent RAG for Real-World University Admissions Counseling**
(arXiv:2507.11272). Hybrid retrieval + multi-agent orchestration deployed at a
Vietnamese university; 6,000+ real interactions over six query categories, ~92%
accuracy, hallucination reduced from 15% to ~1.45%.
*Relation:* they build a system, we build a measurement — but they report a
hallucination number in our domain, at an institution that is squarely our low tier,
and a reviewer will reach for the comparison immediately. Cite it and draw the line
ourselves: an engineered, retrieval-grounded deployment is the mitigation whose
necessity our benchmark measures; their 15% baseline is what an unassisted model does,
which is our object of study.

**B8. The Geometry of Forgetting: Temporal Knowledge Drift as an Independent Axis in
LLM Representations** (arXiv:2605.09195). Distinguishes stale recall from confabulation
and shows the MLP retrieval circuit produces *identical* dynamics for both (r > 0.81,
six models) — the two failure modes are indistinguishable from inside the model, which
is why confidence-based detection fails.
*Impact on claim 2:* the stale/fabricated **concept** is no longer ours alone; their
ground truth is Wikidata-style timelines. What remains ours: ground truth from dated
archives of the primary sources themselves, in a consumer domain where both errors
carry a date and a cost, with the prior value recovered per item rather than inherited
from a curated timeline. Their internals result actually *strengthens* our design: if
the distinction is invisible in the representations, only an external, dated source of
truth can draw it — which is exactly what the benchmark supplies.
**Read in full before submission** — dataset details (reported five-cell taxonomy,
~3.5k queries) are not in the abstract and must be checked before we characterise them.

**B9. Asking For An Old Friend: Temporal Failure Modes in Statutory QA**
(arXiv:2605.23497). 312 expert-validated time-sensitive German statutory QA pairs;
five models × four modes (vanilla, web search, two temporally-filtered RAG variants);
concludes temporal validity must be treated as a hard constraint.
*Relation:* structurally the closest recipe to ours — high stakes, annually shifting
facts, expert-validated, comparable size, same conditions — in a different domain.
Cite as convergent design; our additions are the coverage axis, the language axis, the
interaction question, and the public snapshot trail.

**B10. How often do Answers Change? Estimating Recency Requirements in QA**
(arXiv:2603.16544). RecencyQA, 4,031 questions with recency and stationarity labels;
non-stationary questions are the hardest.
*Relation:* generalises our volatility axis. Our `annual` facts are, in their terms,
high-recency and *stationary* (the change schedule is known: once per cycle) — worth
one sentence in §3, because it sharpens what our axis does and does not vary.

### Consequences applied

1. **Contribution 2 reworded** (draft + outline): from "existing benchmarks score both
   as one kind of error" to "the distinction has been drawn at the representation level
   on curated timelines; we give it primary-source ground truth in a domain where both
   errors have a date and a price."
2. **Interaction (contribution 3) now carries the main weight of novelty.** No found
   work crosses coverage with volatility or pre-commits interpretations.
3. **Contribution 1 (the artifact) unharmed** — still no public admissions dataset
   with archived evidence and measured verification.
