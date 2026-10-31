# ADR-0007 — HMM temporal filter publishes the tremor classification

**Status:** Accepted · **Date:** 2026-10-31 · **Supersedes:** the count state machine (review P1-6)

## Problem

Published `classification` was the raw per-window `score >= 80`; the hysteresis state machine
ran but its output was discarded; its thresholds were hop counts; scores in 56–74 froze it;
`TemporalSmoother` (README's "5-of-10 validator") was never constructed (audit P1-6).

## Decision

Two-state HMM forward filter with rate-based transitions (τ_enter 120 s, τ_exit 60 s), per-window
evidence → likelihood ratio clipped at 60 and tempered by hop/window to account for 87.5 %
window overlap. Publish `confirmed` with hysteresis (0.8 / 0.2). Legacy state names derived
from the posterior. `confidence` column = 100 × posterior.

## Alternatives

Keep counters but in seconds (simpler, still ad hoc); trained classifier (no labelled data);
LR_MAX 400 (confirmed on a single window — too eager for 4 s bursts).

## Trade-off (measured, synthetic)

| | v2.2 | v3 |
|---|---|---|
| Onset latency (median) | 1.1 s | 6.1 s |
| Offset latency (median) | 4.0 s | 8.1 s |
| Specificity (analysis-level) | 0.983 | 1.000 |

Slower to announce, never locks up, hop-invariant (`test_hop_invariance`). For daily
tremor-time estimates, latency of a few seconds is immaterial; for real-time feedback it is a
cost.
