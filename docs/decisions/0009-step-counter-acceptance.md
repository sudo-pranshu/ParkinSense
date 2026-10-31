# ADR-0009 — Keep the v1 step-detection algorithm; rewrite stays experimental

**Status:** Accepted · **Date:** 2026-10-31

## Context
A periodicity-gated rewrite (band-limited magnitude, Verisense-style bouts, autocorrelation
gait check) cut false steps during arm movement on synthetic data (23–80 → 4–12 per minute)
at similar walking error. On the only real walking recording in the repository
(`walking_60s`, ~86 steps expected from its 1.35 Hz spectral cadence) it counted 13–43 steps
across all tested settings; the v1 algorithm counted 75 (69 through the full runtime).

An earlier synthetic walking model lacked the shoulder-pendulum centripetal term and made v1
look 82 % wrong; that model was corrected before any decision was taken.

## Decision
v1 detection logic remains the default (`step_counter.py`, now v1.1: signal time, gap reset,
canonical `walking_state`). The runtime withholds the moving gate while a *rest* tremor is
confirmed: rest-tremor false steps 23/min → 0 with unchanged walking accuracy. The rewrite is
`step_counter_periodic.py`, selectable with `RuntimeEngine(step_counter="periodic")`.

## Open
False steps during non-walking arm movement (~49/min synthetic; 90 in the real
`normal_motion_60s`) remain. Fixing it needs labelled real walking/non-walking data.
