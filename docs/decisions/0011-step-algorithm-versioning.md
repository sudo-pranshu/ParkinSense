# ADR-0011 — Explicit per-algorithm versions; selectable step algorithm

**Status:** Accepted · **Date:** 2026-11-06

## Context

`config.STEP_COUNTER_VERSION = "2.0"` labels recordings, but the default detector is v1.1 (known discrepancy,
`docs/algorithms/ACTIVITY.md`). Changing that constant would alter what historical metadata means.
Sleep and step algorithms now evolve independently of the pipeline, firmware, protocol and capture schema.

## Decision

* `STEP_COUNTER_VERSION` was **not changed** in Phase 7 (historical field); Phase 8 corrected it additively, see [ADR-0013](0013-step-version-label-correction.md).
* New, additive constants: `STEP_ALGORITHM_VERSIONS = {"default": "1.1", "periodic": "2.0", "gated": "3.0-dev"}`,
  `SLEEP_ALGORITHM_VERSION`, `SLEEP_EPOCH_SCHEMA_VERSION`.
* `RuntimeEngine(step_counter="default" | "periodic" | "gated")`; unknown names raise `ValueError` (previously any
  unknown string silently meant the default).
* `metadata.json` gains `step_algorithm`, `step_algorithm_version`, `sleep_algorithm_version`. The 79-column
  capture schema is unchanged.
* The default never changes without meeting a written acceptance rule (`docs/algorithms/STEP_ACCEPTANCE.md`).

## Consequences

Old recordings remain interpretable; new ones say which step algorithm produced them. Analysis outputs
(`sleep` reports, benchmark JSON) carry their own version fields. The label itself was corrected in Phase 8 (ADR-0013).
