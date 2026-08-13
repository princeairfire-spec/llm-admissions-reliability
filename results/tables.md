# Results

256 scored answers.

## Headline: accuracy, abstention and confident error by model

`IN` is the number that matters: a specific wrong fact, stated as fact.

| model | lang | search | n | CO | NA | IN | CGA | F |
|---|---|---|---:|---:|---:|---:|---:|---:|
| gemini-35flash | en | nosearch | 24 | 0.708 | 0.292 | 0.000 | 1.000 | 0.829 |
| gemini-flash | en | nosearch | 42 | 0.524 | 0.476 | 0.000 | 1.000 | 0.688 |
| gemini-flash | ru | nosearch | 1 | 1.000 | 0.000 | 0.000 | 1.000 | 1.000 |
| gemma31b | en | nosearch | 52 | 0.577 | 0.423 | 0.000 | 1.000 | 0.732 |
| gemma31b | ru | nosearch | 52 | 0.538 | 0.462 | 0.000 | 1.000 | 0.700 |

## H1 — coverage tier

| model | tier | n | CO | 95% CI | NA | IN |
|---|---|---:|---:|---|---:|---:|
| gemini-35flash | high | 9 | 0.667 | [0.333, 1.000] | 0.333 | 0.000 |
| gemini-35flash | mid | 8 | 0.875 | [0.625, 1.000] | 0.125 | 0.000 |
| gemini-35flash | low | 7 | 0.571 | [0.143, 0.857] | 0.429 | 0.000 |
| gemini-flash | high | 13 | 0.538 | [0.308, 0.769] | 0.462 | 0.000 |
| gemini-flash | mid | 17 | 0.647 | [0.412, 0.882] | 0.353 | 0.000 |
| gemini-flash | low | 13 | 0.385 | [0.154, 0.615] | 0.615 | 0.000 |
| gemma31b | high | 32 | 0.344 | [0.188, 0.500] | 0.656 | 0.000 |
| gemma31b | mid | 44 | 0.750 | [0.614, 0.864] | 0.250 | 0.000 |
| gemma31b | low | 28 | 0.500 | [0.321, 0.679] | 0.500 | 0.000 |

## H2 — fact volatility

| model | volatility | n | CO | 95% CI | NA | IN |
|---|---|---:|---:|---|---:|---:|
| gemini-35flash | stable | 19 | 0.895 | [0.737, 1.000] | 0.105 | 0.000 |
| gemini-35flash | annual | 5 | 0.000 | [0.000, 0.000] | 1.000 | 0.000 |
| gemini-flash | stable | 29 | 0.793 | [0.621, 0.931] | 0.207 | 0.000 |
| gemini-flash | annual | 14 | 0.000 | [0.000, 0.000] | 1.000 | 0.000 |
| gemma31b | stable | 66 | 0.788 | [0.682, 0.879] | 0.212 | 0.000 |
| gemma31b | annual | 38 | 0.158 | [0.053, 0.289] | 0.842 | 0.000 |

## Interaction — coverage x volatility (exploratory, see DD-001)

Per-cell accuracy. The volatility penalty is stable minus annual within a tier.

| model | tier | stable CO | annual CO | penalty | 95% CI |
|---|---|---:|---:|---:|---|
| gemini-35flash | high | 1.000 | 0.000 | 1.000 | [1.000, 1.000] |
| gemini-35flash | mid | 1.000 | 0.000 | 1.000 | [1.000, 1.000] |
| gemini-35flash | low | 0.667 | 0.000 | 0.667 | [0.333, 1.000] |

**gemini-35flash: interaction (low-tier penalty minus high-tier penalty) = -0.333**

Negative: check for a floor effect before interpreting. If low-tier accuracy is already near zero, volatility has no room to make it worse and this number is an artefact, not a finding (DD-002).

| gemini-flash | high | 0.875 | 0.000 | 0.875 | [0.571, 1.000] |
| gemini-flash | mid | 0.917 | 0.000 | 0.917 | [0.727, 1.000] |
| gemini-flash | low | 0.556 | 0.000 | 0.556 | [0.222, 0.875] |

**gemini-flash: interaction (low-tier penalty minus high-tier penalty) = -0.319**

Negative: check for a floor effect before interpreting. If low-tier accuracy is already near zero, volatility has no room to make it worse and this number is an artefact, not a finding (DD-002).

| gemma31b | high | 0.571 | 0.167 | 0.405 | [0.079, 0.690] |
| gemma31b | mid | 0.941 | 0.100 | 0.841 | [0.612, 1.000] |
| gemma31b | low | 0.667 | 0.200 | 0.467 | [0.111, 0.778] |

**gemma31b: interaction (low-tier penalty minus high-tier penalty) = +0.062**

Positive: volatile facts about low-coverage institutions are worse than the two effects predict separately — a compounding danger zone.


## Error typology — stale vs fabricated

Among wrong answers, how many repeated a previously-correct value rather than inventing one. Well defined even when accuracy is at zero.

| model | tier | volatility | wrong | stale | fabricated | stale share |
|---|---|---|---:|---:|---:|---:|

## H4 — calibration of stated confidence

| model | stated confidence | n | actually correct |
|---|---|---:|---:|
| gemini-35flash | high | 20 | 0.800 |
| gemini-35flash | low | 3 | 0.000 |
| gemini-flash | high | 41 | 0.561 |
| gemini-flash | low | 2 | 0.000 |
| gemma31b | high | 103 | 0.553 |

The damaging pattern is a high share of `high` confidence among wrong answers.

| model | wrong answers | of which stated high confidence |
|---|---:|---:|

## H5 — effect of web search

| model | tier | no search CO | search CO | change |
|---|---|---:|---:|---:|

Search availability is not search usage — a model that had the tool and chose not to use it, then stated a wrong date, is a distinct failure.

| model | answers with search available | at least one search run |
|---|---:|---:|

## Excluded answers

| model | label | count |
|---|---|---:|
| gemini-35flash | ERROR | 10 |
| gemini-flash | ERROR | 75 |

`ERROR` is an API failure, `BLOCKED` a safety-classifier decline, `EMPTY` a response with no text. None of these are the model judging its own knowledge, so counting them as wrong answers would overstate the error rate.
