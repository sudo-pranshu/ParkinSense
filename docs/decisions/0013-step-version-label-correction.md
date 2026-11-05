# ADR-0013 — Correct the step-counter version label additively

**Status:** Accepted · **Date:** 2026-11-06 · **Supersedes:** the "not changed" clause of [ADR-0011](0011-step-algorithm-versioning.md)

## Context

`config.STEP_COUNTER_VERSION` read `"2.0"` and was written into every capture row (`step_counter_version`,
column 51) and `metadata.json`, but the default step counter is the v1 detector, v1.1 (audit finding D1). The
Phase 8 programme asks for the label to be corrected "without breaking old recordings or the capture schema".

## Decision

* The **capture schema is unchanged** (79 columns, `CAPTURE_SCHEMA_VERSION = "3"`); no column is added, removed or
  renamed. Only the *value* written in `step_counter_version` changes for new recordings.
* New recordings write `STEP_ALGORITHM_VERSIONS[engine.step_algorithm]` (`1.1` default, `2.0` periodic, `3.0-dev`
  gated) in capture rows and `metadata.json`. `STEP_COUNTER_VERSION` stays as a **deprecated alias** equal to the
  default's version (`"1.1"`) so importing code keeps working.
* `metadata.json` gains `metadata_revision` (`2`; absent = 1 for all earlier recordings), so a reader can tell
  which meaning the label has.
* `config.step_algorithm_version_of(step_counter_version, step_algorithm, metadata_revision)` is the reader-side
  rule for any recording: a `step_algorithm` key wins (Phase 7 metadata); else revision >= 2 means the label is
  truthful; else the legacy `"2.0"` is read as `"1.1"`, because no other counter was selectable before Phase 7.
* **Existing recordings are never rewritten.**
* `PIPELINE_VERSION` is **not** bumped: no signal processing changed, only a provenance label.

## Consequences

* A CSV capture alone is ambiguous when it shows `2.0`: it may be a legacy default recording or a periodic one.
  Disambiguate with the sibling `metadata.json` (`step_algorithm`, `metadata_revision`). The values are
  distinguishable only through that file; this is a limit of not rewriting history.
* Tests: `tests/unit/test_step_version_label.py` (new labels, schema unchanged, legacy interpretation).
* Golden replay and all pre-existing tests are unchanged (the golden file does not contain the label).
