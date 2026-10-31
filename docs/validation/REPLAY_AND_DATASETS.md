# Replay, datasets and versioning

## Record
```bash
parkinsense-live --firmware-version 4.0   # firmware >= 5 reports itself; pass it for v4
```
Creates `recordings/<time>_<session>/capture.csv` + `metadata.json` (versions, configuration,
measured rate, integrity counters, start/end) and `recordings/latest.json`.

## Replay (deterministic, real pipeline)
```bash
parkinsense-replay recordings/<session>/capture.csv --out replays/run_a
parkinsense-replay data/reference/legacy_serial_23hz/walking_60s.csv --resample   # 23 Hz legacy logs
parkinsense-replay x --compare replays/run_a replays/run_b                        # version-to-version diff
```
Rows are re-framed into the original packets and re-encoded bit-exactly, then fed through
`RuntimeEngine.process_packet` — the live code path. `replay_summary.json` records the source
hash, source pipeline version and replay pipeline version. Outputs never overwrite the source.

## Build a dataset
```bash
parkinsense-dataset recordings/*/capture.csv --out datasets/v1 --version 1.0.0 \
    --labels labels.csv --subjects subjects.json
```
* `labels.csv`: `recording_id,start_s,end_s,label[,subject_id]` (seconds from recording start).
* One row per analysis window (`is_analysis_row`), never per sample.
* Recordings failing QC (non-monotonic time, > 5 % missing, rate > 5 % off, > 1 % v1 gyro at
  full scale, mixed versions) are excluded unless `--include-rejected`.
* `dataset.json` records version, pipeline/schema versions, per-recording QC and label counts.

## Split without leakage
```python
from parkinsense.datasets import splits
train, test = splits.group_split(df, by="subject_id")
splits.assert_no_leakage(train, test)
for subject, tr, te in splits.leave_one_group_out(df): ...
```
Windows overlap 87.5 %; a random window split is never valid.

## Versions to bump
| Change | Bump |
|---|---|
| any change to a published value's definition or temporal behaviour | `PIPELINE_VERSION` (+ ADR) |
| tremor / step / PPG algorithm internals | the matching `*_VERSION` |
| capture columns | `CAPTURE_SCHEMA_VERSION` (append-only) |
| wire format | protocol `version` byte + new decoder branch |
