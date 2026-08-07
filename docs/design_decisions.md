# Design decisions

A dated record of choices made before data collection, and the reasoning behind each.
Written in advance so that outcomes cannot be reinterpreted after the fact.

---

## DD-001 — Claim structure: floor plus upside, not a single bet
*Decided 2026-08-07, before any data collection.*

The paper does not stake its contribution on one statistical test. Three tiers:

1. **Guaranteed.** The artifact: a public admissions-facts dataset with archived
   official-source snapshots, per-item access dates, and a reported disagreement rate
   between two independent verification passes. Plus the abstention / confident-error
   split in a domain with concrete error cost. These exist regardless of what the
   numbers say.
2. **Near-certain.** Main effects for coverage tier and volatility, framed as
   replication of PopQA (2212.10511) and MuLan (2404.03036) in a high-cost domain.
3. **Exploratory.** The coverage × volatility interaction.

**Why:** detecting an interaction of a given size requires roughly four times the
sample needed for a main effect of that size. At ~240 items over 3 tiers × 2 volatility
levels we have ~40 per cell before language and search splits, so the interaction test
is underpowered by construction. A wide confidence interval spanning zero would mean
"we could not distinguish", which is *not* the same as "the effects are additive". The
work must not depend on that test resolving.

## DD-002 — Both interaction outcomes are declared informative in advance
*Decided 2026-08-07, before any data collection.*

Pre-committed interpretations, recorded now so neither can be reverse-engineered later:

- **Additive** → coverage failure and staleness failure are independent mechanisms.
  Retrieval addresses coverage; it does not, on its own, address staleness. Different
  mitigations are required for each.
- **Super-additive** → volatile facts about low-coverage institutions form a distinct
  danger zone, and the practical warning is stronger than either main effect implies.
- **Sub-additive / floor** → low-coverage accuracy is already so low that volatility
  cannot degrade it further. Reported as a floor effect, not as evidence of no
  interaction. See DD-003.

The interaction is reported with confidence intervals, labelled exploratory, and not
converted into a headline claim whatever it shows.

## DD-003 — `prior_year_answer` field and the stale / fabricated error split
*Decided 2026-08-07, before any data collection.*

Each item records the value of the same fact for the previous admissions cycle, in a
`prior_year_answer` field, captured during verification while the official page is
already open.

Every incorrect answer is then classified as:

- **stale** — matches a previously-correct value; the model is behind, not inventing
- **fabricated** — matches no value the fact has ever held

**Why this matters more than it looks:**

1. *It survives a floor effect.* The expected failure mode for annual facts is accuracy
   collapsing toward zero across every coverage tier. If that happens, the interaction
   in DD-002 becomes unmeasurable — low-tier accuracy has nowhere left to fall. But the
   **proportion of errors that are stale rather than fabricated** remains well-defined
   and comparable across tiers even at zero accuracy. It is the analysis that still
   works when the primary one does not.
2. *It is genuinely unoccupied.* MuLan, FreshQA and AbstentionBench all treat an error
   as an error. The distinction between a model that is *out of date* and one that is
   *inventing* has different causes and different fixes, and has not been measured on
   public, snapshot-backed data in this domain.
3. It gives the Analysis section of the paper its actual content.

Cost: seconds per item during verification, since the author is already on the official
page. Cheapest high-value addition available.

## DD-004 — Metric vocabulary borrowed from MSQA
*Decided 2026-08-07.*

Use CO (correct), NA (non-committal / abstention), IN (concretely incorrect), CGA
(correctness given attempt), F (harmonic mean of CO and CGA), following MSQA
(2607.00724). No new metric names are invented.

**Why:** free comparability with a current benchmark, and the CO/NA/IN split is exactly
the abstention-versus-confident-error separation the study needs.

## DD-005 — Volatility levels must avoid a pure floor
*Decided 2026-08-07, pending pilot confirmation.*

`annual` items must not consist solely of facts for a cycle that no model could
plausibly know. A mix is required: some facts from the current published cycle
(potentially within training data) alongside facts for the upcoming cycle. Otherwise
`annual` accuracy sits at zero uniformly and carries no information.

**To be verified in the 20-question pilot** before committing to the full sample: if
pilot accuracy on annual facts is at zero across all tiers, the volatility axis needs
re-specification before Phase 2 begins, not after.
