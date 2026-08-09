# Target venue

Checked 2026-08-09 against the workshop's own pages (tai-eval.github.io, /cfp).

**TAE (Trust-AI-Eval): Can We Trust AI Evaluation?** — NeurIPS 2026 workshop, Sydney,
11–12 December 2026.

| | |
|---|---|
| Submission deadline | **29 August 2026, AoE** |
| Notification | 22 September 2026 |
| Format | up to **8 pages** excluding references and appendices |
| Template | NeurIPS 2026 LaTeX, `\usepackage[dblblindworkshop]{neurips_2026}`, workshop title "TAE (Trust-AI-Eval): Can We Trust AI Evaluation?" |
| Review | double-blind, up to three reviews, via OpenReview |
| Archival | **non-archival** — compatible with the mid-October arXiv preprint and any later full submission |

## Why this workshop and not a generic one

The topics list is nearly a table of contents for our §3: measurement validity and
causal assumptions; benchmark auditing; judge and annotator reliability; domain
coverage and representation gaps; uncertainty and failure-mode reporting. The paper's
strongest material — snapshot-backed ground truth, measured attention checks,
inter-annotator agreement computed against fact-level judgements, the DD log of
pre-committed interpretations — is evaluation methodology first and admissions data
second. Frame the submission accordingly: the admissions domain is the case study, the
trustworthy-measurement protocol is the contribution the workshop asked for.

## Action items this creates

- **Anonymization.** Double-blind: the submission must not link the public GitHub repo
  under the author's name. Standard practice: an anonymized mirror
  (e.g. anonymous.4open.science) linked in the PDF; the named repo goes into the
  camera-ready / arXiv version only. Prepare the mirror in the week before the deadline.
- **Template.** Obtain the official NeurIPS 2026 style file and set the workshop
  option; port `paper/draft.md` into it once results exist (per the outline, after
  Phase 4).
- **Re-run the novelty search** (docs/related_work.md, §3) in late September before the
  arXiv posting, per the fallback plan.
