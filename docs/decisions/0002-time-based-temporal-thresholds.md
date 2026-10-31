# ADR-0002 — Express temporal thresholds in seconds, not call counts

**Status:** Accepted
**Date:** 2026-08-08
**Affects:** `ppg/ppg_processor.py`
**Related:** ADR-0001; engineering audit P0-1; open item P1-6 (state machine)

## Problem

`PPGProcessor` declared its thresholds in seconds and then immediately converted
them to call counts at construction:

```python
self._finger_on_samples_required   = max(int(FINGER_ON_HYSTERESIS_SECONDS * sample_rate), 1)
self._hr_outlier_max_reject_samples = max(int(HR_EMA_OUTLIER_MAX_REJECT_SECONDS * sample_rate), 1)
```

Those counters advance once per `process()` call. The conversion is therefore
only correct if `process()` is invoked exactly once per sample — an assumption
that appears nowhere in the class's documented contract.

It was already wrong before ADR-0001: with `sample_rate=50` (the default) and
samples arriving at 104 Hz, a nominal 1.0 s finger hysteresis was really 0.48 s.
ADR-0001 would have made it far worse — at a 1 Hz analysis rate the same
constant becomes **50 seconds**.

This is the general failure mode behind the whole of audit finding P0-1: a
threshold written as `if counter > 50` cannot be reasoned about without knowing
the call frequency, and the call frequency is a property of a different module.

Notably, SpO₂ publish throttling in the same file was **already** gated on
`time.monotonic()` and was correct throughout. That was the model followed here.

## Constraints

- Public API must not change; `process()` had to keep working identically.
- Must be robust to an injected or rebased clock (test harnesses inject one).

## Alternatives considered

**A. Scale the required counts by the hop.** Restores correct durations but
re-couples the class to the caller's schedule — the exact defect being fixed.
Any future change to the hop silently changes PPG behaviour.

**B. Pass `dt` into each call.** Explicit, but pushes bookkeeping onto every
caller and is easy to get wrong at a call site.

**C. Compare elapsed monotonic time.** Chosen. The class needs no knowledge of
call rate or sample rate; a constant written as 1.0 s means 1.0 s.

## Decision

Replace call counters with monotonic timestamps.

- `_finger_raw_state` / `_finger_raw_since` track the raw detector's verdict and
  when it last changed; the published state follows after
  `FINGER_ON/OFF_HYSTERESIS_SECONDS` of elapsed time.
- `_hr_outlier_reject_since` replaces the reject streak counter; the safety valve
  releases after `HR_EMA_OUTLIER_MAX_REJECT_SECONDS` of wall time.

Elapsed time uses an explicit `is None` check, **not** `or`:

```python
since = self._finger_raw_since
held_for = 0.0 if since is None else now_monotonic - since
```

`or` treats a `0.0` timestamp as absent. `time.monotonic()` is time-since-boot so
this would not bite in production, but any injected or rebased clock starting at
zero would fail silently — and the test harness injects exactly such a clock.

## Consequences

- **Finger detection now takes 1.0 s to confirm, not 0.48 s.** This is the
  documented intent, but it is a behavioural change to a shipped default.
- State transitions are quantised to the analysis hop: a change is only noticed
  when `analyze()` runs. At a 1 s hop, worst-case confirmation is hysteresis +
  one hop. This is inherent to decimated observation, not a defect.
- The class is now independent of both call rate and configured sample rate,
  which partially insulates it from the unresolved PPG rate defect (audit
  Issue #2).

## Open extension

`TremorStateMachine` has the identical defect and remains unfixed. Its
`high_count`/`low_count` are analysis-hop counts, so hop size and detector
behaviour are coupled across two files. It also has a dead-band lock-up: scores
strictly between `LOW=55` and `HIGH=75` increment neither counter, so the state
can freeze with no decay or timeout.

The same reasoning applies — thresholds should read
`if evidence_seconds >= CONFIRM_SECONDS`. Tracked as P1-6.

## Validation

`tests/verify_issue1_ppg_timebase.py` runs the same 3 seconds of held
finger-present at two very different analysis rates:

```text
FINGER_ON_HYSTERESIS_SECONDS   : 1.0
confirm delay @ 104 analyses/s : 1.019 s
confirm delay @ 1 analysis/s   : 2.000 s   (1.0 s hysteresis + 1.0 s hop quantisation)
```

Under the old count-based logic these would have differed by ~100×. The harness
also asserts that `ingest()` buffers without analysing, `analyze()` analyses
without buffering, and `process()` remains equivalent to both.

**Not validated:** DSP is stubbed (scipy unavailable in the review environment).
The time-base logic is fully exercised; the surrounding signal processing is not.
