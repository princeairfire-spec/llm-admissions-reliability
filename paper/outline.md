# Paper outline

Target: 4–8 pages, arXiv preprint, mid-October 2026.

Written now, before results exist, so the framing is fixed in advance rather than fitted
to whatever the numbers turn out to be. Section 5 changes when results arrive; sections
1–4 and 7 should not.

---

## 1. Introduction

Three paragraphs, then the contribution list.

- Applicants increasingly ask chatbots about deadlines, fees and requirements. Cite the
  adoption figures; a wrong deadline costs an application cycle. The cost is asymmetric
  and falls hardest on applicants without access to counsellors.
- What is already known: models are worse on long-tail entities (PopQA), worse on
  mutable facts (MuLan), poorly calibrated about abstention (AbstentionBench), and
  search helps unevenly (FreshQA). **Say this plainly.** The paper is not claiming to
  discover any of it.
- What is not known: whether these failures *compound*, and what they look like in a
  domain where being wrong has a concrete cost.

**Contributions — three bullets, in this order:**

1. A public benchmark of admissions facts, each verified against an archived official
   page, with a stated measurement date and a reported inter-pass disagreement rate.
   No comparable public artifact exists; the closest domain work (arXiv:2511.20653) does
   not release its data.
2. An error typology separating **stale** answers (a previously-correct value) from
   **fabricated** ones. Existing benchmarks score an error as an error; these are
   different failures with different fixes.
3. A measurement of whether coverage and volatility effects **compound**. Reported with
   confidence intervals and labelled exploratory.

## 2. Related work

Grouped as in `docs/related_work.md`: same domain (2511.20653, ImmigrationQA,
CitizenQuery), same axes elsewhere (PopQA, MuLan, FreshQA, AbstentionBench, MSQA,
2504.20022), and the measurement-validity warning (2510.07238).

Be generous. Every one of these did something this paper reuses. A related-work section
that diminishes its predecessors reads as insecurity and invites a hostile review.

## 3. Benchmark construction

- Sampling axes and why each exists; the interaction requirement that drives cell balance.
- The 25 institutions (8 high / 9 mid / 8 low) and the English-source constraint as a
  confound control for the language axis.
- Verification protocol: official page → snapshot → model-assisted extraction under
  five mechanical checks → human acceptance with measured attention controls →
  independent second annotator → delayed intra-annotator pass.
  Prose drafted in `paper/methods_draft.md`.
- **The disagreement rate between passes, reported as a number.** This is the paper's
  claim to data quality; without it "carefully verified" is just a word.
- `prior_year_answer` and why it was collected.

## 4. Experimental setup

Models, prompt (verbatim, in an appendix), what was frozen and when, metrics with the
MSQA citation, and the automatic-vs-human agreement rate from the 50-answer sample.

Report the agreement rate here, not in Limitations. It is a property of the method, and
burying it looks like hiding it.

## 5. Results

One subsection per hypothesis, tables from `results/tables.md`.

Frame H1–H4 as **replication in a high-cost domain**, not as discovery. Then the two
subsections that carry the contribution: the stale/fabricated split, and the interaction.

## 6. Analysis

Error typology with real examples — the actual model outputs, quoted. A model confidently
returning last year's deadline is the paper's most communicable single finding, and one
concrete example does more than a table.

Also: cases where the official source contradicted itself. Those go here, from `notes`.

## 7. Limitations

Long and honest. Reviewers forgive limitations an author names and do not forgive ones
they find themselves.

- **Sample size.** ~240 items, ~40 per interaction cell. Detecting an interaction needs
  roughly four times the sample of a main effect, so the study is underpowered for its
  own exploratory question by construction. Say this in these words.
- **Measurement date.** These numbers are a photograph of August–October 2026 and are
  expected to stop being correct (2510.07238).
- **Tier assignment is a judgement**, not a measurement. Report the Wikipedia-pageview
  robustness check if it was done; say it was not if it was not.
- **Abstention is made salient** by an explicit `I DON'T KNOW` instruction, so the
  measured abstention rate is an upper bound on what an ordinary user would see.
- **Automatic scoring** disagrees with human judgement at a measured rate; report it.
- **Two languages, one of them not low-resource.** Russian is comparatively well
  resourced, so a null result on H3 says little about genuinely low-resource languages.
- **Self-reported confidence** is a weak calibration instrument.
- **Single measurement per question.** No repeated sampling, so run-to-run variance is
  not estimated.

## 8. Conclusion

Short. What was measured, on what, when. No call to action beyond what the data supports.

---

## Submission checklist

- **Author line.** The author.
- **Data and code availability.** Repository URL, commit hash, licence.
- **Tooling statement.** arXiv and most venues ask for a brief note on software and
  tool use. Check the target venue's current wording close to submission — the
  requirements change, and last year's phrasing is often out of date.

---

## When to write `main.tex`

After Phase 4, when there are results to typeset. Writing LaTeX around placeholder
numbers wastes time and quietly encourages fitting the prose to imagined findings.
