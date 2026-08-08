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

Twenty-five institutions, generated from `src/new_item.py` so this table cannot drift
from what the code actually samples. One named degree programme per institution and
level — see the note in that file for why facts are scoped to a programme rather than to
the institution.

| Tier | Institution | Country | Key | Graduate programme sampled | Admissions page |
|---|---|---|---|---|---|
| high | ETH Zurich | CH | `eth` | the MSc in Computer Science | verified |
| high | Harvard University | US | `harvard` | the Master of Science in Computational Science and Engineering | verified |
| high | Imperial College London | GB | `imperial` | the MSc in Computing | verified |
| high | MIT | US | `mit` | the master's program in Electrical Engineering and Computer Science | verified |
| high | National University of Singapore | SG | `nus` | the MComp in Computer Science | verified |
| high | Stanford University | US | `stanford` | the MS in Computer Science | verified |
| high | University of Cambridge | GB | `cambridge` | the MPhil in Advanced Computer Science | verified |
| high | Yale University | US | `yale` | the MS in Computer Science | verified |
| low | American University of Central Asia | KG | `auca` | the MSc in Computer Science | verified |
| low | Chulalongkorn University | TH | `chula` | the MSc in Computer Science | verified |
| low | Innopolis University | RU | `innopolis` | the MSc in Computer Science | verified |
| low | MBZUAI | AE | `mbzuai` | the MSc in Computer Science | verified |
| low | Nazarbayev University | KZ | `nazarbayev` | the MSc in Computer Science | verified |
| low | Universitas Indonesia | ID | `indonesia` | the master's program in Computer Science | verified |
| low | Ural Federal University | RU | `urfu` | the MSc in Computer Science | verified |
| low | Vietnam National University | VN | `vnu` | the MSc in Information Technology | verified |
| mid | Aalto University | FI | `aalto` | the MSc in Computer Science | verified |
| mid | KAIST | KR | `kaist` | the master's program in Computer Science | verified |
| mid | KTH Royal Institute of Technology | SE | `kth` | the MSc in Computer Science | verified |
| mid | TU Delft | NL | `delft` | the MSc in Computer Science | verified |
| mid | Technical University of Munich | DE | `tum` | the MSc in Informatics | verified |
| mid | Trinity College Dublin | IE | `trinity` | the MSc in Computer Science | verified |
| mid | Universiti Malaya | MY | `malaya` | the MSc in Computer Science | verified |
| mid | University of Bologna | IT | `bologna` | the second cycle degree in Artificial Intelligence | verified |
| mid | University of Warsaw | PL | `warsaw` | the MSc in Computer Science | verified |

"Admissions page" says whether a URL has been verified with an HTTP request or whether
the page list still falls back to a site-scoped search for it.

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

## Change log

**2026-08-08 — Oxford replaced by Cambridge.** Every `ox.ac.uk` page returns HTTP 403 to
a non-browser request, so its pages cannot be archived. An item whose snapshot cannot be
taken has no evidence behind it and fails the verification protocol, so Oxford is not
usable here. Cambridge is the same tier and the same country and answers normally, so
the sampling design is unchanged.

This belongs in the paper's Limitations as a sentence: institutions that block automated
archiving are excluded by construction, which is a mild selection effect on the
`high` tier — the very universities most targeted by scrapers are the most likely to
block them.

## Institutions considered and not included

Recording these so the selection is not silently post-hoc:

- **ETH Zurich, NUS, Tsinghua** — arguably `high` rather than `mid`, which would have
  made the mid tier harder to fill. Left out to keep the tiers separated.
- **Regional universities with no English admissions pages** — would have given a
  cleaner `low` tier, but break criterion 1 and confound H3.
