# Pilot: 20 questions, end to end

The point of the pilot is not to produce results. It is to hit every problem in the
design while the cost of fixing it is one afternoon rather than thirty hours of
annotation. Do not skip to Phase 2 because the pilot "obviously" works.

## Composition of the 20

Balance matters even at this size, because two of the checks below need all six cells
populated:

| | annual | stable |
|---|---:|---:|
| high | 3 | 3 |
| mid | 3 | 3 |
| low | 4 | 4 |

Four universities is enough at this stage: one high, one mid, two low.

## Steps

**1. Archive the pages first, answers second.**

```bash
python3 src/collect.py https://<official-page> <item-id>
```

Read the answer off the archived copy, not the live page. If the page changes between
archiving and reading, the snapshot no longer supports the recorded answer.

**2. Write the items into `data/benchmark.jsonl`.**

One JSON object per line. `data/benchmark.example.jsonl` shows the shape. Fill
`prior_year_answer` while the page is open — going back for it later costs far more
than getting it now, and it is what makes the stale/fabricated analysis possible.

**3. Validate.**

```bash
python3 src/validate.py
```

Fix every error. Read every warning.

**4. Cost check before spending anything.**

```bash
python3 src/run_eval.py --model opus5 --limit 20 --dry-run
```

**5. One model, English, no search.**

```bash
python3 src/run_eval.py --model opus5 --limit 20 --languages en --modes nosearch
```

**6. Score and look at the actual answers.**

```bash
python3 src/score.py
head -3 results/scored.jsonl | python3 -m json.tool
```

Read a dozen raw answers by hand. This is the step people skip and regret.

**7. Then widen: both languages, both modes, one model.**

```bash
python3 src/run_eval.py --model opus5 --limit 20
python3 src/score.py && python3 src/analyze.py
```

## The four questions the pilot has to answer

**1. Is accuracy on `annual` facts at zero across every tier?**

If yes, the volatility axis needs re-specifying **before** Phase 2, not after (see
docs/design_decisions.md DD-005). A floor leaves the interaction test nothing to
measure. The fix is to include annual facts from the *current published* cycle
alongside the upcoming one, so there is a range rather than a wall.

**2. Does the scorer agree with you?**

Read all 20 English no-search answers by hand and compare with `label` in
`results/scored.jsonl`. Any disagreement is a normaliser bug, and finding it now is
worth more than finding it in 960 answers. Common causes: a date format not covered by
`extract_dates()`, an abstention phrased in a way not in `ABSTENTION_MARKERS`, a gold
answer whose `acceptable_variants` are too narrow.

**3. Do models actually abstain, ever?**

If `NA` is exactly zero across 20 questions the prompt is probably not being read as
permission. Check the raw text: are models saying "I'm not certain, but..." and then
giving a figure? That phrasing is currently scored `IN`, which is arguably right — but
it is a judgement call that belongs in the paper, and it should be made deliberately.

**4. Is `prior_year_answer` ever actually matched?**

If no wrong answer matches a prior-year value, either the models are not being stale
(a real and interesting finding) or `prior_year_answer` is not filled in on enough
items to detect it. Check which before concluding anything.

## What "the pilot succeeded" means

Not "the accuracy numbers look interesting." It means: the pipeline runs end to end,
the scorer agrees with you on 20 hand-checked answers, and none of the four questions
above turned up something that requires changing the design. If one did, change the
design now and re-run the pilot. That is the pilot doing its job, not failing.
