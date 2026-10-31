# ADR-0001 — Separate per-sample streaming from per-window analysis

**Status:** Accepted
**Date:** 2026-08-08
**Affects:** `runtime/runtime_v2.py`, `pipelines/motion_pipeline.py`, `ppg/ppg_processor.py`
**Related:** Engineering audit finding P0-1; ADR-0002; ADR-0003

## Problem

The windowed analysis gate sat inside the per-sample decode loop:

```python
for i in range(BATCH_SIZE):
    ...
    if len(gx_buffer) == WINDOW_SIZE:      # deque(maxlen=416): true forever
        result = pipeline.process(...)
```

Because the buffer is a fixed-capacity `deque`, the condition holds permanently
once filled. `MotionPipeline.process()` therefore ran ~104×/s on a window that
had advanced by one sample — 99.76% overlap between consecutive analyses.

Observed consequences:

- `TremorStateMachine` counts *calls*. Its `high_count >= 2` threshold, designed
  as ~2 windows (8 s), was executing in **19 ms**. The hysteresis presented in
  the README as the primary false-positive defence performed no temporal
  filtering at all.
- `PPGProcessor` converted second-denominated constants to sample counts via
  `fs`, assuming one call per sample. Finger hysteresis nominally 1.0 s was
  really 0.48 s.
- ~100× more CPU than the analysis required, plus 104 JSON rewrites and 104
  `flush()` calls per second.

## Constraints

- Must not break step detection or PPG. Both consume samples, not windows.
- Must preserve the raw signal at full rate for replay and dataset use.
- Must not restructure the pipeline's module boundaries.

## Alternatives considered

**A. Add a hop counter around the existing block.** This was the original audit's
recommendation and it is **wrong**. `StepCounter.update()` and PPG buffer
ingestion both lived inside that block and are genuinely per-sample —
`StepCounter` is a threshold/hysteresis/refractory state machine that misses
steps if samples are skipped, and `PPGProcessor`'s rolling buffer *is* the PPG
waveform, so decimating ingestion decimates the signal. Applied literally this
would have broken two subsystems silently.

**B. Throttle only the metrics output.** Leaves the CPU cost and the degenerate
state machine untouched. Treats the symptom.

**C. Split the loop body into two paths.** Chosen.

**D. Event-driven scheduling on a wall-clock timer.** Cleaner in principle, but
introduces a second thread contending with the BLE callback for pipeline state,
and makes replay non-deterministic (analysis boundaries would depend on machine
speed). Rejected primarily for the replay determinism.

## Decision

Two explicit paths in the decode loop.

**Per sample:** buffer appends, `pipeline.ingest_ppg()`, `StepCounter.update()`,
capture row.

**Per hop:** windowed motion analysis, PPG analysis, metrics, JSON, console.

`PPGProcessor.process()` was split into public `ingest()` + `analyze()`;
`process()` remains as `ingest + analyze` so existing callers are unaffected.

`ANALYSIS_HOP_SAMPLES = SAMPLE_RATE_HZ // 2` — a **0.5 s hop**, 87.5% overlap,
2 Hz biomarker update.

### On hop size

Two corrections to earlier reasoning in this record, both material.

**Correction 1 — the CPU justification was wrong.** The hop was first set to
1.0 s on cost grounds. That does not survive arithmetic: one analysis is ~1–3 ms
in CPython (dominated by numpy call overhead), so every hop from 0.25 s to 2 s
costs under ~1.2% of a core. **CPU stops being a discriminator below ~10 Hz** and
cannot justify any choice in this range.

**Correction 2 — confirmation takes 4 hops, not 6.** An earlier draft of this
record claimed 6, by assuming `high_count` resets on the NO_TREMOR → POSSIBLE
transition. It does not; it accumulates. Verified directly against
`TremorStateMachine`:

```text
hop 1: NO_TREMOR         high=1
hop 2: POSSIBLE_TREMOR   high=2
hop 3: POSSIBLE_TREMOR   high=3
hop 4: CONFIRMED_TREMOR  high=4
```

The real constraint is **evidence independence**. With a 4 s window, fully
independent estimates arrive only every 4 s; any shorter hop produces correlated
scores that `TremorStateMachine` nonetheless counts as independent votes.

| Hop | Overlap | Time to CONFIRMED (4 hops) | Cold start (+4 s window fill) | Assessment |
|---|---|---|---|---|
| 0.25 s | 93.75% | 1.0 s | 5.0 s | Four near-duplicate votes; confirmation is not evidence |
| **0.5 s** | **87.5%** | **2.0 s** | **6.0 s** | **Chosen** |
| 1.0 s | 75% | 4.0 s | 8.0 s | Defensible, more latency than necessary |
| 2.0 s | 50% | 8.0 s | 12.0 s | Risks missing short episodes |

Window overlap in the 50–75% range is conventional for windowed inertial
analysis (Banos et al., *Window Size Impact in Human Activity Recognition*,
Sensors 14(4), 2014); 87.5% is slightly above that range, accepted deliberately
in exchange for a 2 Hz dashboard update, since the correlation cost is borne by
the state machine rather than by any individual estimate.

**Open coupling:** hop size and state-machine thresholds form a single latency
budget split across two files. ADR-0002's rationale extends to the state machine,
which should become time-based so the hop becomes a pure cost knob. Until then,
changing this constant silently changes detection latency.

## Consequences

- Biomarker updates drop from ~104 Hz to 2 Hz. The dashboard polls at 100 ms and
  re-reads identical values between updates.
- `PIPELINE_VERSION` bumped 2.1.0 → 2.2.0. Recordings either side of this change
  are not interpretable under the same temporal assumptions, and the version
  string is currently the only way to tell them apart (see review P0-3).
- `StepCounter` receives a motion state up to one hop (0.5 s) stale. That state
  derives from a 4 s window, so the staleness sits inside its existing smoothing.
- `TremorStateMachine`'s 2/4 thresholds now mean 1 s/2 s of sustained evidence.
  Its **dead-band lock-up is confirmed empirically, not theoretical**: scores
  strictly between `LOW=55` and `HIGH=75` increment neither counter, and 20
  consecutive hops at score 65 leave the machine in `CONFIRMED_TREMOR` with
  counters frozen at high=5, low=0, with no decay and no timeout. At 104 Hz,
  noise crossing a threshold masked this; at 2 Hz it is reachable. **Unfixed —
  tracked as review P1-6.**
- `PPGProcessor.process()` now has zero callers; retained as a compatibility
  shim.
- An exception inside `pipeline.process()` is swallowed by bleak and retries per
  sample until metrics exist — a silent storm. **Unfixed;** tracked as P1-7.

## Validation

`tests/verify_issue1_scheduling.py`, over 4000 synthetic samples:

```text
pipeline.process calls : 69     (was 3585 — 52× reduction)
pipeline.ingest calls  : 4000   (all samples)
StepCounter.update     : 3585   (all samples)
capture rows written   : 3585   (all samples)
step increments        : 66, of which 65 on non-analysis rows
```

Three harness bugs were found and fixed while building it:

1. A wrong assertion — `packet_count` legitimately changes per packet, not per
   sample.
2. A bad stimulus — feeding 4000 samples in milliseconds of wall clock made
   `StepCounter`'s 0.3 s refractory reject everything. An artifact of replaying
   faster than real time, confirmed by testing the detector directly (57–60
   steps per 30 s at 120 spm) and fixed by injecting a simulated clock.
3. A **non-discriminating assertion** — the step-freshness check originally
   compared distinct step values against the number of analyses. At a 0.5 s hop
   and ~2 steps/s those rates coincide, so the test failed on a correct
   implementation. Replaced with a hop-independent check: whether the step
   column ever advances on a row where no analysis ran. It does, 65 times out of
   66, which is only possible if the column is written per sample.

**Not validated:** the real pipeline has never been executed end-to-end. scipy
could not be installed in the review environment, so both harnesses stub the DSP
layer. Hardware validation outstanding — and this is precisely the gap the
replay framework (review P1-5) is meant to close permanently.
