# Budget

## Measured on the free tier, 2026-08-07

Not estimates — results of actual calls against a real Google AI Studio free-tier key.
Free-tier quotas are per project and change without notice, so re-measure rather than
trusting this.

**The binding constraint is input tokens, not request count.** The quota ids returned
in a 429 are `GenerateContentInputTokensPerModelPerDay-FreeTier` and
`...PerMinute-FreeTier`. Planning a sweep by counting requests, as the table further
down does, understates the limit for anything that inflates the input.

| Condition | Result |
|---|---|
| `gemini-3.6-flash`, no search | **Works.** ~152 input tokens per call. This is the workhorse. |
| `gemini-2.5-pro`, no search | **Daily quota exhausted after ~2 calls.** Not usable for a 960-call sweep. |
| `gemini-3.6-flash`, with search | **429 on every attempt**, including after a 75-second wait with no other traffic. |

**Consequence for H5.** Grounding appears to push a single request past the
per-minute *input token* cap on its own, so the search condition is effectively
unavailable free. This is one afternoon's observation and could be a transient quota
state — worth one retry after a daily reset before concluding. But plan for H5 being
unavailable rather than assuming it will work.

That is not a disaster. H5 is the hypothesis most thoroughly covered by prior work
(FreshQA), and the brief's own cut order puts conditions ahead of questions. The
recommended plan is:

- **Core study:** `gemini-3.6-flash`, both languages, no search. 240 x 2 = 480 calls.
- **Second model:** `gemini-3.5-flash-lite` (higher daily cap) for a model-comparison row.
- **H5:** deferred. If it matters enough, one Anthropic model with search costs about
  $14 — buy the hypothesis rather than the whole sweep.

**One local pitfall, since it cost an hour:** Python installed from python.org on macOS
ships without CA certificates and cannot make *any* HTTPS request until
`/Applications/Python 3.x/Install Certificates.command` is run. `curl` works fine
throughout, which makes the failure look like a bad API key when it is not.

---


Computed 2026-08-07, before any paid run. Prices are the published Anthropic API rates
at that date and should be re-checked before the full sweep.

## The size of the experiment

| Axis | Values | Multiplier |
|---|---|---|
| Questions | 240 | 240 |
| Language | en, ru | 2 |
| Search | off, on | 2 |
| Models | 3 | 3 |

240 x 2 x 2 = **960 calls per model**, **2,880 calls total**.

## Token assumptions

| | input | output |
|---|---:|---:|
| No search | ~250 | ~400 |
| With search | ~3,750 | ~400 |

The prompt plus one question is short. Output is larger than the visible answer because
adaptive thinking is billed as output. The search figure is dominated by retrieved page
content injected into the request — this is where the money goes, not the questions.

## Cost per model, full sweep (960 calls)

| Model | $/Mtok in | $/Mtok out | no search | with search | total |
|---|---:|---:|---:|---:|---:|
| `claude-opus-5` | 5.00 | 25.00 | $5.40 | $13.80 | **$19.20** |
| `claude-sonnet-5` | 3.00 | 15.00 | $3.24 | $8.28 | **$11.52** |
| `claude-haiku-4-5` | 1.00 | 5.00 | $1.08 | $2.76 | **$3.84** |

**API subtotal: ~$35.**

Web searches are billed separately from tokens, at roughly $10 per 1,000 searches. At
one search per search-mode call, 1,440 searches across three models is **~$14**.

**Total for the full study: ~$49.** With the pilot, one re-run after a bug, and slack:
**budget $75.** This is not a number that should constrain the design.

## What to cut if it ever does

In this order, per the brief:

1. **Fewer models.** Dropping to two saves roughly a third and costs the least
   scientifically — the model axis is the least interesting one here.
2. **Fewer conditions.** The search axis is where the money is; H5 is the most
   expendable hypothesis.
3. **Never fewer questions.** Cell counts are already thin for the interaction test
   (docs/design_decisions.md DD-001). Cutting questions is the one saving that would
   make the study unable to answer its own question.

## Open models

The brief calls for open small models via free Colab. These cost nothing but the
author's time, and time is the actual scarce resource here — running a 7B model on a T4
is an afternoon of setup for one more row in the results table. Recommendation: get the
full pipeline working on the API models first, and treat open models as an extension
only if there is time after the paper draft exists. If they are added, `run_eval.py`
needs one new backend function; nothing else in the pipeline changes, because
`results/raw/` is just JSONL.

## Watch the first real run

`run_eval.py` records `input_tokens` and `output_tokens` on every row, so actual spend
can be checked against this estimate after the pilot:

```bash
python3 -c "import json,glob; rows=[json.loads(l) for f in glob.glob('results/raw/*.jsonl') for l in open(f) if l.strip()]; print(sum(r['input_tokens'] for r in rows), 'in;', sum(r['output_tokens'] for r in rows), 'out')"
```

If the search-mode input tokens are far above 3,750 per call, re-do this table before
launching the full sweep rather than after.
