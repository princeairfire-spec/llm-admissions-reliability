# Annotation tracker

Where to find each institution's facts, and what is done so far.

`python3 src/progress.py` prints live progress from `data/benchmark.jsonl` — this file
is the reference for *where to look*, that command is the reference for *what is left*.

## Status of the links below

Checked 2026-08-07 with an HTTP request. **Verified** means the page answered 200 that
day. It may still 404 next month — MBZUAI's `study/admissions` did exactly that between
being indexed by a search engine and being opened here, which is itself evidence for the
paper's premise. If a link is dead, use the search link in the same row and update this
file.

## Where to look

| Institution | Tier | Admissions page | Campus / general facts |
|---|---|---|---|
| MBZUAI | low | [graduate-admission-process](https://mbzuai.ac.ae/study/graduate-admission-process/) ✅ · [undergraduate](https://mbzuai.ac.ae/study/undergraduate-admission-process/) ✅ | [fast-facts](https://mbzuai.ac.ae/about/fast-facts/) ✅ |
| MIT | high | [gradadmissions.mit.edu/programs/deadlines](https://gradadmissions.mit.edu/programs/deadlines) ✅ | [mit.edu](https://www.mit.edu/) |
| TU Delft | mid | [admission-and-application](https://www.tudelft.nl/en/education/admission-and-application/msc-international-diploma) ✅ | [tudelft.nl/en](https://www.tudelft.nl/en/) |
| Trinity College Dublin | mid | [postgraduate/how-to-apply](https://www.tcd.ie/study/postgraduate/how-to-apply/) ✅ | [tcd.ie](https://www.tcd.ie/) |
| KAIST | mid | [admission.kaist.ac.kr/intl-graduate](https://admission.kaist.ac.kr/intl-graduate/) ✅ | [kaist.ac.kr/en](https://www.kaist.ac.kr/en/) |
| Universitas Indonesia | low | [penerimaan.ui.ac.id/en](https://penerimaan.ui.ac.id/en) ✅ | [ui.ac.id/en](https://www.ui.ac.id/en/) |
| Harvard | high | [search](https://www.google.com/search?q=site%3Aharvard.edu+graduate+admissions+deadline) | [harvard.edu](https://www.harvard.edu/) |
| Stanford | high | [search](https://www.google.com/search?q=site%3Astanford.edu+graduate+admissions+deadline) | [stanford.edu](https://www.stanford.edu/) |
| Oxford | high | [search](https://www.google.com/search?q=site%3Aox.ac.uk+graduate+admissions+deadline) | [ox.ac.uk](https://www.ox.ac.uk/) |
| University of Bologna | mid | [search](https://www.google.com/search?q=site%3Aunibo.it+second+cycle+degree+enrolment+deadline) | [unibo.it/en](https://www.unibo.it/en) |
| Nazarbayev University | low | [search](https://www.google.com/search?q=site%3Anu.edu.kz+graduate+admission+deadline) | [nu.edu.kz](https://nu.edu.kz/) |
| Innopolis University | low | [search](https://www.google.com/search?q=site%3Ainnopolis.university+admission+master+deadline) | [innopolis.university/en](https://innopolis.university/en/) |

✅ = responded 200 on 2026-08-07. No mark = find it via the search link, then replace the
link here so the next pass is faster.

## What to look for, per fact

| Fact key | Look for | Volatility | Usual location |
|---|---|---|---|
| `deadline` | The date applications close | annual | admissions / academic calendar |
| `tuition` | Annual fee as a number with a currency | annual | admissions, or a separate fees page |
| `english` | Minimum TOEFL iBT total score | annual | admissions → language requirements |
| `documents` | How many referees or recommendation letters | annual | admissions → required documents |
| `eligibility` | Required prior degree or minimum GPA | stable | admissions → entry requirements |
| `language` | Language of instruction | stable | programme page |
| `duration` | How many years or semesters | stable | programme page |
| `city` | City of the main campus | stable | about / contact / fast facts |

## Rules while annotating

**Official pages only.** Not rankings, not aggregators, not Wikipedia. If it is not on
the university's own site, the item does not exist.

**Skip rather than infer.** If the page gives a range, a conditional, or nothing at all,
press Enter and move on. MBZUAI's tuition is the standard example: full scholarships mean
there may be no single annual figure. A skipped item costs nothing; a guessed one
poisons the results and cannot be detected later.

**Copy, do not retype.** The gold answer and the quote are copied from the page. Retyping
introduces errors that look exactly like model errors when scored.

**Record contradictions in `notes`.** A page that disagrees with another page on the same
site is a finding for the Analysis section, not a problem with the data.

## Progress

```bash
python3 src/progress.py
```
