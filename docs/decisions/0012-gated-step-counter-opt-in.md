# ADR-0012 — Gated step counter stays opt-in

**Status:** Accepted · **Date:** 2026-11-06

## Context

Production v1.1 over-counts irregular arm movement badly and under-counts regular walking on real labelled
recordings (Clemson, 90 recordings: Regular −22 %, Irregular +299 %). A candidate (`GatedStepCounter`, autocorrelation
walking gate with retroactive credit) was built and evaluated against criteria written before any candidate result
(`docs/algorithms/STEP_ACCEPTANCE.md`), with thresholds chosen by participant-independent cross-validation.

## Result

Held-out: MAPE 18.2 % vs 111.1 %, F1 0.753 vs 0.639 (paired CI of the F1 gain +0.092 … +0.134); Karas false steps 4.1 vs
52.5 per non-walking minute. But **two criteria failed**: SemiRegular MAPE 20.9 % vs 8.2 % (A2) and Karas walking-state
sensitivity 0.900 vs 0.973 (A5).

## Decision

Production remains the default. The candidate is selectable with `RuntimeEngine(step_counter="gated")`, recorded as
such in metadata, and documented as experimental. Not adopted despite its large gains because a clear regression on a
realistic condition (walking with stops/turns) violates "do not replace working algorithms without proving they are
better".

## Failed or rejected experiments

* Existing `periodic` counter (CV-based bout rule): overall bias −37 % on Clemson.
* Shorter gate window (3.2 s, hold 3 s, credit 3 s) was added to the cross-validated grid after the first result; it was selected for one fold, and the held-out SemiRegular MAPE stayed at 20.9 % (vs 8.2 %). It is much worse at low thresholds (mean condition MAPE 47.8 at ρ 0.6, RMS 0.08 g).
* Lower autocorrelation thresholds: false steps on irregular movement return (all 30 participants, RMS floor 0.08 g: Irregular bias +52 % at ρ 0.6; +94 % at ρ 0.55 on a 10-participant subset).

## Next

A hybrid (production counting inside gate-confirmed bouts plus a lower-threshold bout onset) and ParkinSense-hardware
trials are the open routes; neither was attempted. Re-evaluate under the same acceptance rule.
