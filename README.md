# LLM Admissions Reliability

How reliably do language models answer factual questions about university admissions,
and where do their errors concentrate?

Prospective applicants increasingly ask chatbots about deadlines, fees and document
requirements. A wrong deadline costs an application cycle. This repository contains a
benchmark of admissions facts verified against archived official university pages, and
an evaluation of several language models on it.

**Status:** Phase 0 (novelty check) complete — see [docs/related_work.md](docs/related_work.md).
Pipeline written and smoke-tested on synthetic data. Data collection has not started.

## Workflow

```bash
pip install -r requirements.txt
export ANTHROPIC_API_KEY=...

python3 src/collect.py <official-url> <item-id>   # archive the page
python3 src/validate.py                            # schema, cell balance, duplicates
python3 src/run_eval.py --model opus5 --dry-run    # cost before spending
python3 src/run_eval.py --model opus5 --limit 20 --languages en --modes nosearch
python3 src/score.py --sample 50                   # label answers + hand-check sample
python3 src/analyze.py                             # tables
python3 src/analyze.py --agreement                 # automatic vs human agreement
```

Start with [docs/pilot_checklist.md](docs/pilot_checklist.md). The pilot exists to find
design problems while they are cheap to fix.

## Documents

| File | What it is |
|---|---|
| [docs/related_work.md](docs/related_work.md) | Phase 0: nearest prior work and where this project's contribution actually sits |
| [docs/design_decisions.md](docs/design_decisions.md) | Dated decisions made **before** data collection, so outcomes cannot be reinterpreted afterwards |
| [docs/universities.md](docs/universities.md) | The twelve institutions and why each was chosen |
| [docs/budget.md](docs/budget.md) | Cost of the full sweep, computed before any paid run |
| [docs/pilot_checklist.md](docs/pilot_checklist.md) | The 20-question pilot and the four questions it must answer |
| [docs/code_walkthrough.ru.md](docs/code_walkthrough.ru.md) | Line-by-line explanation of every script, in Russian |

## Repository layout

```
data/
  benchmark.jsonl     final dataset
  snapshots/          archived official pages — the evidence for every gold answer
  schema.json         validation schema
prompts/              versioned prompts, dated; frozen once runs begin
src/
  collect.py          download and archive snapshots
  validate.py         schema validation, cell balance, duplicate detection
  run_eval.py         model runs
  score.py            metrics
  analyze.py          tables and figures
results/raw/          raw model outputs — written once, never edited
paper/main.tex
notebooks/
docs/                 working notes
```

## Ground rules

- `results/raw/` is append-only. Every derived number is recomputed from it, so any
  result in the paper can be traced back to a raw model response.
- Every gold answer has an archived snapshot and an access date. Numbers change; the
  snapshot is what makes the measurement checkable later.
- All findings are reported as measured, including null and unflattering ones.

## Measurement date

All reported figures are a snapshot of the web as of the dates recorded per item in
`data/benchmark.jsonl`. Admissions facts change annually; the numbers here are not
expected to remain correct, and that is the point of the study.

## Author

Work by the repository owner.
