# Institution list

Fixed 2026-08-07. Twelve institutions, four per coverage tier. Adding or removing an
institution after data collection begins changes what the coverage axis measures, so
this list is frozen alongside the prompts.

## Selection criteria

1. **Official admissions pages in English.** Non-negotiable, and it is a
   confound control rather than a convenience: if some institutions publish only in
   English and others also in Russian, then a Russian-language question is asking about
   a different information environment depending on the institution, and the language
   effect (H3) can no longer be separated from the source-language effect. Holding the
   source language constant means the language axis tests the language of the *question*
   and nothing else.
2. **All six `fact_type` values are answerable** for the institution, so cell balance
   is achievable without special-casing.
3. **A published prior-year value exists** for at least some annual facts, so
   `prior_year_answer` can be filled (see docs/design_decisions.md DD-003).

## The list

| Tier | Institution | Country | Notes |
|---|---|---|---|
| high | Harvard University | US | |
| high | MIT | US | |
| high | University of Oxford | GB | |
| high | Stanford University | US | |
| mid | TU Delft | NL | |
| mid | Trinity College Dublin | IE | |
| mid | KAIST | KR | |
| mid | University of Bologna | IT | |
| low | MBZUAI | AE | |
| low | Nazarbayev University | KZ | |
| low | Innopolis University | RU | |
| low | Universitas Indonesia | ID | |

## On the tier assignment

`coverage_tier` is a proxy for how much an institution appears in English-language
training data. It is assigned **per institution, once**, not per item — otherwise the
axis drifts and the interaction test in DD-001 becomes uninterpretable.

The assignment is a judgement call, and the paper must say so. The three tiers are
intended as ordinal and coarse: top-of-mind globally / well known regionally / limited
English-language presence. They are not a measurement.

**Worth doing if time allows, as a robustness check:** record an objective proxy per
institution — English Wikipedia pageviews over a fixed window is the usual choice, and
it is what PopQA (arXiv:2212.10511) uses for entity popularity — and report whether it
agrees with the hand assignment. If it does, the tier axis is defensible; if it does
not, the disagreements are worth a paragraph. This does not need to be done before
collection starts, but it is cheap and it closes an obvious reviewer question.

## Institutions considered and not included

Recording these so the selection is not silently post-hoc:

- **ETH Zurich, NUS, Tsinghua** — arguably `high` rather than `mid`, which would have
  made the mid tier harder to fill. Left out to keep the tiers separated.
- **Regional universities with no English admissions pages** — would have given a
  cleaner `low` tier, but break criterion 1 and confound H3.
