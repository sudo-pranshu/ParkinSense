# ADR-0003 — Mixed time bases within the capture file

**Status:** Accepted
**Date:** 2026-08-08
**Affects:** `runtime/runtime_v2.py` (`CAPTURE_COLUMNS`, `_write_capture_row`)
**Related:** ADR-0001; open items P0-2, P0-3, P1-9

## Problem

ADR-0001 decimated windowed analysis to a 1 s hop while keeping sample ingestion
at 104 Hz. That immediately raises the question of what a capture row means.

The first implementation wrote **every** column from the forward-filled metrics
snapshot. That was wrong for three column groups, and the error was not caught
until an adversarial re-review:

- `timestamp` (wall clock) repeated 104× then jumped.
- `sample_count` stopped being unique per row, so it could no longer serve as a
  row index.
- **All nine step columns collapsed to 1 Hz.** `StepCounter` was still running
  per sample, but its output was only *sampled* at the analysis rate — quantising
  step *timing* to the hop.

The step regression was the serious one. Step timing is the basis of every
cadence and gait claim the project makes, and the capture file is simultaneously
the research dataset, the replay source, the validation data, and the future ML
training set. Silently quantising it would have poisoned all four, invisibly.

## Constraints

- Column order and count must not change (the dashboard reads by position and
  name; existing captures must stay comparable).
- A recording must be re-analysable offline at a different hop and reproduce the
  same result — otherwise replay is impossible.

## Alternatives considered

**A. One row per sample, all columns forward-filled.** Simple, and wrong for the
reasons above.

**B. One row per analysis.** Discards 99% of the raw signal. Makes replay and any
future re-analysis impossible. Rejected outright.

**C. Two files — a per-sample raw capture and a per-analysis metrics file.**
Arguably the cleanest design: each file has one unambiguous time base. Rejected
*for now* because it requires a join to reconstruct, breaks the dashboard's
single-file read, and doubles the lifecycle surface — but it remains the better
long-term structure and should be revisited alongside P0-2.

**D. One row per sample, columns grouped by their natural time base.** Chosen.

## Decision

Three explicit groups within one row, documented in `_write_capture_row`'s
docstring:

| Group | Columns | Rationale |
|---|---|---|
| **Per-sample (live)** | raw signal, wall clock, runtime counters, all nine step fields | These describe a *sample*. `StepCounter` is a streaming detector; sampling it at the analysis rate destroys timing resolution |
| **Per-analysis (forward-filled)** | tremor, motion context, HR, HRV, SpO₂, SQI | These describe a *window*. A 4 s verdict was never specific to the one sample whose arrival triggered it, so forward-filling is what it always meant implicitly |
| **Per-packet** | `packet_version`, `flags` | Taken from the packet this sample arrived in, not the last analysed one |

`CAPTURE_COLUMNS` was extracted as a named constant and `_write_capture_row`
asserts row length against it, so the 60-element header and the 60-element row
can no longer drift apart silently.

## Consequences

- Recordings retain full raw and step resolution, so offline re-analysis at a
  different hop is possible — a precondition for replay.
- The JSON/console view of step counts (analysis-rate snapshot) and the CSV view
  (per-sample) now differ. Two views of the same quantity; not incorrect, but a
  consumer comparing them will see a discrepancy.
- `walking_state` is derived in two places (metrics dict and capture row). A
  duplication introduced here; tracked as P2-12.

## Known gaps — not addressed by this ADR

- **No `is_analysis_row` marker (P0-2).** Nothing distinguishes the row where
  analysis ran from the ~103 forward-filled copies. Any per-row ML training
  over-represents each windowed label ~104× and leaks the same window across
  train/test splits unless grouped. **This is the highest-priority open item
  against the capture format.**
- **`PIPELINE_VERSION` not bumped (P0-3).** Captures from before and after
  ADR-0001 are indistinguishable by metadata despite different temporal
  semantics.
- **No monotonic host clock (P1-9).** The two time columns are wall clock
  (NTP-steppable) and device `micros()` (wraps every 71.6 min, unhandled).
  Neither is reliably monotonic over a long recording.

## Validation

`tests/verify_issue1_scheduling.py` asserts column time bases directly rather
than only row counts:

```text
distinct sample_count values : 3585 (rows: 3585)   -> unique per row
distinct packet_count values : 359  (~rows/10)     -> tracks packets, not analyses
distinct steps values        : 67   (analyses: 35) -> per-sample resolution held
distinct tremor_score values : 1    (analyses: 35) -> forward-filled as intended
```

The step assertion discriminates: under the original implementation it would
have shown ≤35 distinct values and failed.
