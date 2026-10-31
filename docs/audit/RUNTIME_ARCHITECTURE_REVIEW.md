# ParkinSense Runtime — Post-Issue-#1 Architecture Review

**Scope:** the runtime as it exists after the Issue #1 scheduling change.
**Method:** every modified file re-read from scratch, assumptions from the original audit discarded.
**Status:** review only. No code changed. Nothing here is implemented.

**Severity scale**

| | Meaning |
|---|---|
| **P0** | Corrupts data, or invalidates a scientific claim. Fix before any dataset is collected or any result is published. |
| **P1** | Serious defect or a documented feature that does not exist. Fix before external review. |
| **P2** | Real problem with a workaround. Fix before the architecture is built on further. |
| **P3** | Cleanliness, ergonomics, latent traps. |

---

## Summary

The Issue #1 change is sound and I would keep it. The two-clock split is the right abstraction and the verification harnesses are meaningful.

But reading the whole runtime cold, the scheduling fix exposed a more serious problem underneath it: **the runtime is not yet capable of producing a trustworthy research dataset**, for reasons that have nothing to do with scheduling. Two modules the README presents as features are empty files. The capture file can be silently truncated by an unrelated import. Nothing marks which CSV rows carry fresh analysis, so any naive ML use will over-represent windowed labels by ~104×. And the pipeline version string did not change despite a modification that altered every temporal behaviour in the system — meaning recordings from before and after Issue #1 are indistinguishable from their own metadata.

Those are the P0s. They matter more than anything remaining in the original audit, because they compromise the artefact the project exists to produce.

---

## P0 — Data corruption or scientific invalidity

### P0-1 · Capture file is opened at import and closed only on `KeyboardInterrupt`

**Location:** `runtime_v2.py:139–146`, `549–556`

```python
csv_file = open("realtime_capture_v2.csv", "w", newline="")
writer = csv.writer(csv_file)
writer.writerow(CAPTURE_COLUMNS)
```

This executes at **module import**, in mode `"w"`. Two distinct failures:

1. **Truncation on import.** Importing `runtime_v2` for any reason — a test, a tooling script, an editor's autocomplete engine, `python -c "import ..."` to read a constant — destroys the previous capture. My own verification harness had to `chdir` into a temp directory specifically to avoid this, which is the clearest possible signal that the lifecycle is wrong.
2. **Data loss on every exit path except Ctrl-C.** `csv_file.close()` appears only in the `except KeyboardInterrupt` branch. If the device isn't found, `main()` returns normally; if BLE drops, `async with BleakClient` exits and `main()` returns; on `SIGTERM`, nothing runs. In each case the final buffered rows are lost and the file is closed only incidentally by interpreter shutdown.

**Why it happens.** File ownership is module-level rather than session-level. There is no object whose lifetime corresponds to "one recording".

**Effect.** Tremor/HR/HRV/SpO₂/activity: none on live values. **Dataset integrity: severe** — silent loss of the tail of every non-Ctrl-C session, and total loss of a prior capture on an unrelated import. Latency/power: none.

**Fix.** A `CSVRecorder` owning `open`/`writerow`/`flush`/`close`, constructed when a session starts, used as a context manager. Filename should include a session timestamp so a new run cannot overwrite an old capture at all.

**Alternatives considered.** (a) Open in append mode — avoids truncation but concatenates unrelated sessions into one file with repeated headers. (b) Move the `open()` into `main()` — fixes truncation-on-import with a two-line change but leaves the close paths unfixed. (b) is a reasonable stopgap; (a) is worse than the status quo.

**Trade-off.** Timestamped filenames break the dashboard, which hardcodes `realtime_capture_v2.csv`. Needs a `latest` symlink or a small manifest file.

---

### P0-2 · Nothing marks which rows carry fresh analysis

**Location:** `runtime_v2.py:_write_capture_row`, `CAPTURE_COLUMNS`

By design (and correctly), windowed biomarker columns are forward-filled between analyses. At a 1 s hop that means **104 consecutive rows carry the identical tremor score, severity, frequency, HR, HRV and SpO₂**.

Nothing in the file distinguishes the row where analysis actually ran from the 103 copies that follow it.

**Effect.** This is the single biggest future-ML hazard in the codebase.

- Anyone training a per-row classifier gets each windowed label repeated ~104 times. Sample counts are inflated 104×, standard errors shrink by ~10×, and any cross-validation split that isn't grouped by window **leaks the same window into train and test**. Reported accuracy would be meaningless and inflated.
- Any statistical summary over the CSV (mean tremor score, % time in tremor) is implicitly weighted by row count, which is uniform — so it happens to be correct for time-weighting, but only by accident, and only while the hop is constant.
- The problem is invisible. Nothing errors; the numbers just come out wrong and confident.

**Fix.** Add an `is_analysis_row` boolean column, and an `analysis_seq` integer that increments per analysis. Grouped cross-validation then becomes `groupby("analysis_seq")`, and filtering to fresh rows becomes trivial. Cost: two columns.

**Alternatives.** (a) Write a separate metrics CSV at the analysis rate and join on timestamp — cleaner separation, but two files to keep aligned and a join to get wrong. (b) Leave biomarker cells empty on non-analysis rows — self-documenting, but breaks every naive `pandas` consumer and the dashboard's plotting. **(a) is arguably the better long-term design**; the boolean column is the far cheaper 90% fix.

---

### P0-3 · `PIPELINE_VERSION` was not bumped for a change that altered every temporal behaviour

**Location:** `runtime_v2.py:20`

```python
PIPELINE_VERSION = "2.1.0"   # unchanged across Issue #1
```

The comment directly above it states the contract: *"Bumped whenever the runtime/pipeline processing logic changes in a way that would affect how a captured dataset should be interpreted later."*

Issue #1 changed the analysis rate by 104×, changed the meaning of every `TremorStateMachine` threshold from samples to seconds, and changed finger-detection hysteresis from 0.48 s to 1.0 s. A recording from before and after is **not interpretable under the same assumptions** — and carries the same version string.

**Effect.** Any longitudinal comparison across that boundary silently mixes two different systems. For a platform whose entire premise is longitudinal monitoring, this is a first-order correctness problem.

**Fix.** Bump to `2.2.0` (or `3.0.0` — the temporal semantics changed, which is arguably breaking). Additionally record `ANALYSIS_HOP_SAMPLES` and `SAMPLE_RATE_HZ` as their own capture columns, so the hop is recoverable from the data rather than inferred from a version string that someone must remember to bump.

**This one is nearly free and should be done immediately regardless of what else is decided.**

---

### P0-4 · Actual stream rate is computed but never validated against the nominal rate

**Location:** `runtime_v2.py:38, 126`, `sampling_rate` in metrics

```python
SAMPLE_RATE_HZ = 104
WINDOW_SIZE = SAMPLE_RATE_HZ * 4
```

Every frequency-domain result depends on `fs` being genuinely 104 Hz. The runtime *already computes* the observed rate (`sample_count / elapsed`) and publishes it as a metric — and then never compares it to the constant.

If the device actually streams at, say, 98 Hz (BLE congestion, the firmware's bounded catch-up scheduler snapping forward, a dropped connection event), then:

- The "4 second" window is really 4.24 s.
- Welch is told `fs=104` for data sampled at 98 → **every reported frequency is scaled by 104/98 = 1.061**.
- A genuine 5.0 Hz tremor reports as 5.31 Hz. Still inside the 4.0–6.5 Hz scoring gate, so nothing looks wrong — the number is just wrong by 6%.

**Effect.** Tremor: systematic frequency bias, silent. Activity: cadence bias. HR/HRV/SpO₂: compounded on top of the separate PPG rate defect (Issue #2). This is a scientific-validity problem dressed as a performance metric.

**Fix.** On startup, measure the arrival rate over the first few seconds and compare against `SAMPLE_RATE_HZ`. Warn loudly beyond ~2% and refuse beyond ~5%, or — better — derive `fs` from measured packet timestamps and pass the measured value into the pipeline. Record both nominal and measured rate in the capture.

**Trade-off.** Deriving `fs` dynamically makes results depend on link quality, which is its own reproducibility hazard. My recommendation is to *measure, record, and warn* but keep processing at a fixed declared rate, so the data carries enough information to detect and correct the bias offline.

---

## P1 — Serious defects and documented features that do not exist

### P1-5 · `replay_v2.py` and `build_dataset.py` are empty files

**Location:** `dashboard/python/replay/replay_v2.py` — **0 bytes**. `dashboard/python/dataset/build_dataset.py` — **0 bytes**.

The README lists "Replay framework for algorithm validation" under Software Platform, "Replay" as an Android feature, `replay/ # Offline replay framework` and `dataset/ # Dataset generation utilities` in the repository structure, and cites replay as a validation method.

**None of it exists.** These are empty placeholder files.

**Effect.** The project's stated validation strategy — "allowing new algorithms to be compared against consistent reference recordings" — has no implementation. There is currently **no way to re-run a recorded session through the pipeline**, which means no regression testing against real data, no offline algorithm comparison, and no way to demonstrate that Issue #1 (or any future change) preserved behaviour on real signals.

This is the highest-value missing component in the repository. It is also now *easy* to build, because the capture format after Issue #1 carries per-sample raw signal — feeding those rows back through `notification_handler`'s inner loop is nearly all a replay tool needs.

**Recommendation.** Build replay next, before Issue #2. Every subsequent audit fix becomes verifiable against real recordings instead of synthetic stubs.

---

### P1-6 · `TremorStateMachine` is still coupled to the hop

**Location:** `state_machine.py:21–61`

You raised this and you're right — it is the last hop-coupled component, and my Issue #1 change made the coupling *load-bearing* by giving the counters a defined unit (hops) rather than a meaningless one (samples).

Current thresholds are call counts: `high_count >= 2` → POSSIBLE, `>= 4` → CONFIRMED. Change the hop and detector behaviour changes silently, in a different file.

There is also a lock-up independent of the hop, now **confirmed empirically rather than inferred**. Scores strictly between `LOW=55` and `HIGH=75` increment neither counter:

```python
if score >= HIGH:   self.high_count += 1; self.low_count = 0
elif score <= LOW:  self.low_count  += 1; self.high_count = 0
# 56..74 -> both counters frozen
```

Driving the real class: after reaching `CONFIRMED_TREMOR`, **20 consecutive hops at score 65 leave it in `CONFIRMED_TREMOR`** with counters frozen at high=5, low=0. No decay, no timeout, no recovery. At 104 Hz noise crossing a threshold masked this; **at 2 Hz it is reachable.**

Note also that confirmation takes **4 hops, not 6** — `high_count` is not reset on the NO_TREMOR → POSSIBLE transition, it accumulates. An earlier draft of this review and of ADR-0001 both stated 6; both were wrong and have been corrected.

**Fix — and I agree with your framing.** Convert to elapsed time:

```python
if evidence_seconds_high >= CONFIRM_SECONDS: ...
```

Then 0.25 s, 0.5 s and 1 s hops all behave identically, and hop size becomes a pure cost/responsiveness knob with no detector semantics attached. Add explicit decay for the dead band so the state cannot freeze.

**Better long-term alternative.** The counter machine is an ad-hoc approximation of a two-state hidden Markov model. Replacing it with a Bayesian filter — observation likelihood from the tremor score, transition priors from published tremor-episode duration statistics — yields a calibrated posterior probability of tremor rather than a hard label, is straightforwardly defensible to an IEEE reviewer, and makes the confidence output meaningful instead of a re-scoring of the same features. This is the version I would want in the paper. It is a larger change and should be its own issue.

---

### P1-7 · Exceptions in the BLE handler are swallowed, and now retry per sample

**Location:** `runtime_v2.py:421` (`or not state.metrics`), bleak's notification dispatch

Bleak logs and discards exceptions raised inside a notification callback. If `pipeline.process()` raises — a malformed buffer, a scipy edge case, a `KeyError` on a renamed metric — the handler dies silently for that packet.

The `or not state.metrics` clause forces analysis until metrics exist. So a persistent exception produces a **silent retry at the full sample rate**, with no log line, no counter, and a dashboard that just keeps showing `WAITING`.

**Fix.** Wrap the analysis block in `try/except`, count failures, expose the count as a metric, and log the first occurrence with a traceback. Escalate to stopping the capture after N consecutive failures rather than spinning.

---

### P1-8 · No packet sequence number — loss is undetectable

**Location:** packet header `<BBHI>` (`version`, `flags`, `reserved`, `timestamp_us`)

Dropped BLE notifications are invisible to the runtime. It sees a gap in device timestamps and never checks for one. The firmware discards `notify()`'s return value (`(void)result;`) so the device doesn't know either.

**Effect.** A recording with 5% packet loss looks identical to a clean one. Every downstream rate calculation, every window that spans a gap, and every cadence estimate is quietly wrong. For a research platform this is a data-provenance failure.

**Fix.** The header has an unused 16-bit `reserved` field — use it as a packet sequence counter. Costs zero bytes and is backward-compatible if the version byte is bumped. Host-side, track expected-vs-received and record loss rate per session.

---

### P1-9 · No monotonic host clock in the capture

**Location:** `_write_capture_row` writes `time.time()`; device time is `sample_timestamp_us`

The capture has exactly two time columns: host wall clock (subject to NTP steps, DST, manual changes) and device `micros()` (which wraps every 71.6 minutes with no host-side unwrap — original audit P1-10).

For a recording of any length, **neither column is reliably monotonic.**

**Fix.** Add a `host_monotonic` column from `time.monotonic()`. One column, no downside, and it makes every recording internally consistent regardless of what the wall clock does.

---

## P2 — Real problems with workarounds

### P2-10 · Non-atomic metrics write meets a bare `except` in the dashboard

`runtime_v2.py:580` truncates and rewrites `realtime_metrics_v2.json`; `realtime_dashboard_v2.py:75–80` reads it every 100 ms inside `try: ... except: metrics = {}`.

A read landing between truncation and completion raises `JSONDecodeError`, is swallowed by the bare `except`, and the dashboard renders **all defaults** — `WAITING`, zeros — for that frame. Indistinguishable from a genuinely idle device.

Reducing writes from 104 Hz to 1 Hz shrank the window considerably (a strict improvement), but did not close it.

**Fix.** Write to a temp file and `os.replace()` (atomic on POSIX and Windows). Separately, narrow the dashboard's `except` to `(OSError, json.JSONDecodeError)` and keep the previous frame's metrics rather than blanking.

### P2-11 · `MotionPipeline` owns `PPGProcessor` — an ownership violation my fix made more visible

`motion_pipeline.py:38` constructs a `PPGProcessor`. PPG has no relationship to motion processing; it lives there for call-site convenience. Issue #1 forced me to add an `ingest_ppg()` passthrough purely to reach it — a wrapper that exists only because ownership is wrong.

This is also the mechanism behind Issue #2 (the `PPGProcessor()` default `fs=50`) and Issue #5 (`motion_state` never passed): both are consequences of the runtime not owning the PPG processor directly.

**Fix.** The runtime should own `MotionPipeline` and `PPGProcessor` as siblings, exactly as it already owns `StepCounter`. This deletes `ingest_ppg()`, makes the sample rate explicit at construction, and makes passing `motion_state` a one-liner. **Doing this before Issue #2 and Issue #5 would make both trivial** — worth sequencing that way.

### P2-12 · Duplicated `walking_state` derivation — introduced by me

`"WALKING" if step_data["walking"] else "NOT_WALKING"` now appears in both the metrics dict and `_write_capture_row`. Two places to change, and a real risk the JSON and CSV disagree.

**Fix.** One `_walking_label(step_data)` helper, or have `StepCounter` return the canonical label.

### P2-13 · No reset path for reconnect or session restart

`state`, the six deques, `StepCounter` and `PPGProcessor` all carry state across a BLE gap. `StepCounter.reset()` and `PPGProcessor.reset()` exist and are documented for exactly this — **neither is ever called.**

After a 30-second dropout, the motion window silently splices pre-gap and post-gap samples into one "4 second" buffer, and cadence is computed across the discontinuity.

### P2-14 · No session identifier

Concatenating captures from multiple sessions produces an ambiguous dataset. A `session_id` (UUID or start timestamp) column solves it for one column's cost.

---

## P3 — Cleanliness and latent traps

| # | Issue | Location |
|---|---|---|
| P3-15 | `ANALYSIS_HOP_SECONDS` is defined and never used inside the module — dead by my own stated rules. Either use it in the status output or drop it. | `runtime_v2.py:79` |
| P3-16 | `state.packet_count += 1` runs *before* the length validation, so malformed packets inflate the count and the derived `sampling_rate`. | `runtime_v2.py:316` |
| P3-17 | `if state.metrics:` uses dict truthiness as a "has analysis run" sentinel. Fragile; an explicit `analysis_count: int` is clearer and enables P0-2's `analysis_seq`. | `runtime_v2.py:421, 589` |
| P3-18 | `_write_capture_row` takes 11 positional args *and* reads module globals (`state`, `writer`, `start_time`). Untestable in isolation. Should take a `Sample` dataclass. | `runtime_v2.py:223` |
| P3-19 | `PPGProcessor.process()` now has zero callers repo-wide. Retained for API compatibility — should carry an explicit deprecation note with a removal target. | `ppg_processor.py` |
| P3-20 | `sampling_rate` is computed in two places with the same expression. | `runtime_v2.py:304, 561` |
| P3-21 | `MotionPipeline.process(ir=None, red=None)` uses magic-`None` to mean "already ingested". Documented, but an implicit contract. Explicit `analyze_only=True` would be clearer. | `motion_pipeline.py` |
| P3-22 | `reserved` header field unused (see P1-8 for a use). | packet format |

---

## Design exploration: could the tremor detector be streaming?

You asked this to expose hidden assumptions. It does.

**The hard constraint is not implementation, it is physics.** Resolving a 0.4 Hz difference in the tremor band requires roughly 1/0.4 ≈ 2.5 s of observation. That is the time–frequency uncertainty relation, not a property of Welch's method. **No streaming reformulation can produce 0.4 Hz frequency resolution from less than ~2.5 s of data.** Any claim to the contrary in a paper would be wrong.

So streaming cannot reduce detection *latency*. What it can change is *cost* and *continuity*:

| Approach | Per-sample cost | Gives | Verdict |
|---|---|---|---|
| **Welch (current)** | O(N log N) per block | Full spectrum, entropy, centroid | Correct; cost irrelevant on a host at 1–2 Hz |
| **Goertzel** | O(1) per bin | Magnitude at chosen bins | ~12 bins × 3 axes ≈ 36 recursive filters. Still block-output. **Compelling for the Android/firmware port**, not for numpy on a laptop |
| **Sliding DFT** | O(1) per bin, truly recursive | Continuously updated bins | Marginally stable — pole on the unit circle, needs damping. Known numerical hazard |
| **Resonator + envelope** | O(1) | Continuous tremor-band *amplitude* | Loses frequency resolution entirely |

**My recommendation: none of these as a replacement.** But a *hybrid* is genuinely attractive and is close to what commercial wearables do:

- **Continuous** band-power via a 4–6.5 Hz resonator plus envelope detector — O(1) per sample, gives a responsive amplitude signal between analyses.
- **Periodic** spectral refinement at the hop for dominant frequency, band ratio, entropy, centroid — where the resolution actually has to come from.

That yields a responsive amplitude trace for the dashboard *and* rigorous spectral features for the detector, with an honest story about which quantity updates at which rate. It also directly addresses your "cheap motion state every sample" question, since the same envelope machinery answers it.

For the firmware/Android port, **Goertzel is the right answer** and worth noting in the paper as the on-device strategy.

---

## Recommended sequencing

The original audit ordered work by defect severity. After this review I would reorder, because some fixes make later ones dramatically cheaper:

1. **P0-3** — bump `PIPELINE_VERSION`, record hop and sample rate as columns. Minutes of work, prevents dataset ambiguity accumulating from today.
2. **P0-2** — add `is_analysis_row` / `analysis_seq`. Two columns, prevents a whole class of invalid ML results.
3. **P0-1** — `CSVRecorder` with proper lifecycle. Unblocks componentization and stops silent data loss.
4. **P1-5** — build replay. **Every subsequent change becomes verifiable against real recordings instead of stubs.** This is the force multiplier.
5. **P2-11** — move `PPGProcessor` ownership to the runtime. Makes audit Issues #2 and #5 near-trivial.
6. **Issue #2** (PPG rate chain) — now testable via replay.
7. **P1-6** — time-based state machine, then the Bayesian filter as a separate research change.
8. **P0-4, P1-7, P1-8, P1-9** — rate validation, error handling, sequence numbers, monotonic clock.

Note that item 4 changes the character of the whole project: right now every fix is verified against synthetic stubs, which is why I have twice had to tell you "not validated on hardware". Replay closes that gap permanently.

---

## What I would not change

- **The two-clock split.** Correct abstraction; keep it.
- **File-based decoupling of runtime and dashboard.** Genuinely good; it is what makes replay feasible at all.
- **Forward-filling windowed columns.** Correct — provided P0-2's marker column is added.
- **A third UI clock.** Still not justified. Publishing is microseconds; revisit when cloud sync lands.
- **The 4 s window.** Set by the frequency resolution the tremor band requires. Do not shorten it for responsiveness — that trade is unavailable, per the uncertainty argument above.
