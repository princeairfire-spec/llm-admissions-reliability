# Prompts

**Frozen on first use.** Once a prompt has produced a single row in `results/raw/`, it
is immutable. Changing it invalidates every run made with it, because the results would
then mix two different experimental conditions. If a prompt genuinely has to change,
add `v2_<date>_<lang>.txt` and re-run everything; do not edit `v1`.

| File | Purpose |
|---|---|
| `v1_2026-08-07_en.txt` | English condition |
| `v1_2026-08-07_ru.txt` | Russian condition — a translation of the English one, not a separate design |

`{question}` is replaced with `question_en` or `question_ru` from the benchmark item.
Nothing else is substituted: no institution hints, no date, no few-shot examples. Every
model sees the same text.

## Why each part is there

**"Answer with the specific fact and nothing else."** Without this, models return a
paragraph, and scoring turns into judging prose. The instruction is not there to make
models look worse — it makes automatic scoring possible and equally so for every model.

**The explicit `I DON'T KNOW` permission.** This is load-bearing for H4. If the prompt
does not say abstention is allowed, a model that guesses cannot be distinguished from a
model that was told it had to answer, and the headline finding — that models rarely
abstain even when abstention is invited — is not measurable. The wording says outright
that abstention is *correct behaviour*, so a model choosing to guess anyway is doing so
against an explicit invitation. That is the finding.

**The `CONFIDENCE:` line.** Feeds the calibration analysis: whether a model's stated
confidence tracks whether it is actually right. Self-reported confidence is a weak
instrument and the paper should say so, but it costs one line and is the only
confidence signal available uniformly across open and closed models.

## Known limitation, to state in the paper

The exact string `I DON'T KNOW` makes abstention easy to detect automatically, but it
also makes abstention *salient* in a way an ordinary user's prompt would not. The
measured abstention rate is therefore an upper bound on what a real user would see —
which strengthens rather than weakens H4: if models rarely abstain even when handed
the phrase, they abstain less often in the wild. Say this in Limitations rather than
leaving it for a reviewer to find.
