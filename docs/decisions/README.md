# Architecture Decision Records

Each ADR captures one significant decision: the problem, the alternatives that
were genuinely considered, why the chosen option won, what it costs, and how it
was validated.

**Why this exists.** Months from now — writing the IEEE paper, debugging a
regression, onboarding a collaborator, or revisiting a threshold — the code will
show *what* was decided but not *why*, and not what was rejected. Reconstructing
that from a diff is unreliable. These records also make the reasoning citable in
the paper: a reviewer asking "why a 4 s window?" or "why this hop?" should get an
answer with a justification and a stated trade-off, not a constant.

**When to write one.** Any change that alters a scientific claim, a temporal
constant, a data format, a module boundary, or an externally visible contract.
Not for bug fixes that restore intended behaviour.

**Status values.** `Proposed` · `Accepted` · `Superseded by ADR-NNNN` · `Rejected`

Superseded records are never deleted. The history of a decision is often more
useful than its current state.

## Index

| ADR | Title | Status |
|---|---|---|
| [0001](0001-two-clock-runtime-scheduling.md) | Separate per-sample streaming from per-window analysis | Accepted |
| [0002](0002-time-based-temporal-thresholds.md) | Express temporal thresholds in seconds, not call counts | Accepted |
| [0003](0003-capture-column-time-bases.md) | Mixed time bases within the capture file | Accepted |
| [0004](0004-package-structure.md) | One `parkinsense` package; dead code removed | Accepted |
| [0005](0005-motion-spectral-features.md) | Tremor features on the un-band-passed spectrum; context excludes tremor band | Accepted |
| [0006](0006-runtime-engine.md) | Pure RuntimeEngine on signal time | Accepted |
| [0007](0007-tremor-hmm.md) | HMM temporal filter publishes the tremor classification | Accepted (supersedes the count state machine) |
| [0008](0008-ppg-rate-and-quality.md) | PPG at the true slot rate, owned state, explicit quality | Accepted |
| [0009](0009-step-counter-acceptance.md) | Keep the v1 step-detection algorithm; rewrite stays experimental | Accepted |

## Template

```markdown
# ADR-NNNN — <short imperative title>

**Status:** Proposed | Accepted | Superseded by ADR-NNNN
**Date:** YYYY-MM-DD
**Affects:** <files, subsystems, data formats>
**Related:** <audit findings, issues, other ADRs>

## Problem
What was wrong, and how it was observed rather than assumed.

## Constraints
What the solution had to preserve.

## Alternatives considered
Each with why it was rejected. Include the option that was nearly chosen.

## Decision
What was done, and the reasoning that decided it.

## Consequences
Behavioural changes, including regressions accepted knowingly.

## Validation
What was tested, how, and what remains unverified.
```
