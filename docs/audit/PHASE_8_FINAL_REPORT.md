# Phase 8 final report — wear-aware continuous monitoring

Branch `transform/engineering-overhaul`. Date 2026-11-06. Authoring: Pranshu Kumar (all commits).

## Evidence classes used in this report

| Class | Phase 8 |
|---|---|
| Implemented | host wear monitor, runtime hook, offline CLI, step-label correction, benchmark, documentation |
| Automated-test verified | pytest (see §8), host firmware `g++` tests and type-checks |
| Host-simulated | synthetic wear/removal/fault scenarios; simulated BLE packets |
| Research-dataset evaluated | false-removal rates on Walch and Karas (other devices) |
| **Physically hardware-tested** | **no documented test.** Update 2026-11-06: the owner reports having tested the updated firmware, dashboard and system on themselves and that it worked; no version/profile, test IDs, durations, logs or measurements were provided, so this is owner-reported evidence only and every individually documented test stays NOT RUN ([plan §3a](../validation/PHASE_8_VALIDATION_PLAN.md#3a-owner-reported-physical-testing-2026-11-06)). The board is stated to be the Seeed XIAO nRF52840 |
| **Externally validated / clinically validated** | **nothing** |

## 1. Initial audit

* Repository state: branch `transform/engineering-overhaul`, clean, no stashes; PR #3 had already merged the branch into
  `origin/develop` (merge `edbaa1a`). `develop` was not modified by Phase 8.
* Firmware 5.0.0: host-tested only — never compiled with the nRF52 core, flashed or measured. v4 is the last
  hardware-verified build.
* `REQUIRE_FINGER_FOR_STREAMING` gates IMU reads, packet construction/`seq`/timestamps and `notify()`; not PPG polling
  or advertising. No write characteristic exists (no downlink). Table in the
  [architecture](../architecture/WEAR_AWARE_ACQUISITION.md).
* Hardware: LSM6DS3 + MAX30102 (finger sensor) + battery; no skin-contact/proximity/temperature sensor; INT not wired;
  wiring undocumented; a prototype photo appears to show an ESP32-S3-labelled board (documented BOM says nRF52840) —
  logged as test W0.
* Device bridge: the linked computer reports a Linux VM with no serial devices and no PPK2; no hardware was reachable.

## 2. Research performed

Cloned and read: Open Wearables, OpenEarable v1 and v2, InfiniTime, GGIR, ParaDigMa, pdathome_tremor, Oxford
ssl-wearables (licences, structure, relevant sources). Read: the Nature tremor paper (PMC text), OWEAR site, UCI /
PhysioNet / NSRR / Radboud / arXiv landing pages for 13 datasets. Mid-phase an additional mandate (public-dataset-first
research) arrived and was folded in as the dataset register and benchmark registry; its ingestion framework and baseline
reproductions are Phase 9.

## 3. Open-source projects evaluated

Nine rows: [register](../research/OPEN_SOURCE_WEARABLE_REVIEW.md). Decisions: Open Wearables, OWEAR, OpenEarable v1/v2,
InfiniTime → reference-only; ParaDigMa/pdathome_tremor, GGIR → benchmark/methodology; Oxford → reject; PPK2 → adopt as
the measurement instrument. Bradykinesia/dyskinesia/FoG/wear-state repositories beyond GGIR were **not** reviewed.

## 4. Licence decisions

InfiniTime GPL-3.0: no code reuse (would relicense the MIT firmware). OpenEarable 2: custom text, reference-only.
Oxford Academic Use Licence: excluded. Apache-2.0 sources: usable later with NOTICE and a separate `third_party/`
copy; nothing copied now. Dependencies added: none. [Attribution file](../research/LICENCES_AND_ATTRIBUTION.md).

## 5. Architecture decisions

[ADR-0013](../decisions/0013-step-version-label-correction.md) (version label) and
[ADR-0014](../decisions/0014-wear-aware-acquisition.md): host-side opt-in wear monitor; five separate concepts; joint
evidence for removal; faults are no evidence; no firmware or protocol change; hardware selection deferred.

## 6. Code changes

| Area | Change |
|---|---|
| `parkinsense/wear/` (new) | `WearMonitor`, `WearConfig`, state enums, `analyze_arrays`; `api.py` CLI `parkinsense-wear` |
| `parkinsense/runtime/engine.py` | opt-in `wear_monitor`; REMOVED forces step gate REST; step-version label now algorithm-specific |
| `parkinsense/runtime/recorder.py` | `metadata_revision`, truthful `step_counter_version`; `wear` block only when enabled |
| `parkinsense/config.py` | `STEP_COUNTER_VERSION` is a deprecated alias of `"1.1"`; `METADATA_REVISION`, `step_algorithm_version_of()` |
| `benchmarks/wear_bench.py` | public-data false-removal evaluation |
| CI | profile-B sketch type-check step |
| Docs | review, dataset register, benchmark registry, architecture, validation plan, power guide, ADRs, cross-reference updates |

## 7. Hardware changes

None. Options (capacitive pad, proximity, temperature, fusion) are documented with cost/power/integration/reliability;
nothing selected or ordered.

## 8. Test results

| Check | Result | Class |
|---|---|---|
| `pytest` (bare, as CI) | **139 passed**, 1 deselected (`-m 'not hardware'`: the physical-device test, skipped because no board is reachable) — up from 110 | automated |
| New: `tests/unit/test_wear.py` (22), `tests/unit/test_step_version_label.py` (7) | passed | automated / host-simulated |
| Golden replay and all pre-existing tests | passed unmodified | automated |
| flake8 CI rule set, `check_doc_links.py` (249 links), markdownlint-cli2 | 0 problems | automated |
| `g++` packet tests; sketch type-check profile A and profile B | OK | host firmware |
| Physical hardware tests (H0–H11, W0–W8, PPK2 S1–S7) | **NOT RUN** | — |

Phase 8 acceptance: the software and documentation criteria are met; the hardware-dependent criteria (wear detection,
removal, re-wear, power, overnight, BLE reconnection on firmware 5.0.0) are **unmet and pending**. Phase 8 is therefore
**not complete**.

## 9. Benchmark results (public data, other devices)

`python -m benchmarks.wear_bench` (150 s): 15 usable Walch worn nights, 27 Karas driving recordings.

| Quantity | Result |
|---|---|
| Pooled worn-sleep epoch SD (1 s, max axis) q01/q05/q25/q50 | 0.89 / 1.06 / 1.39 / 1.83 mg |
| Share of worn night in still runs ≥ 15 min at 1 / 2 / 4 / 8 / 13 mg | 0 / 3.3 / 13.2 / 27.9 / 36.2 % |
| State machine, PPG absent (worst case): mean REMOVED at 1 / 2 / 4 mg | 0 / 6.7 / 42.5 % (subjects ever REMOVED 0 / 5 / 12 of 15) |
| Shipped default (1 mg) on Karas driving, 623 min | 0 % REMOVED |
| Monitor cost (Python, aarch64 sandbox) | 3.1 µs/sample |

## 10. Before / after

| | Before | After |
|---|---|---|
| Wear awareness | none; silence when no finger | opt-in host inference, independent of PPG |
| Step-version label in new recordings | `2.0` for the v1.1 default | `1.1` (algorithm that ran); `metadata_revision: 2` |
| Default engine output, golden replay, capture schema | — | unchanged (79 columns) |
| Firmware, protocol | — | unchanged |
| Current / battery life | unmeasured | **still unmeasured** |

## 11. Known limitations

REMOVED is inferred and rarely triggers at the fail-safe default; removal sensitivity is unmeasured (no public non-wear
labels, no hardware data); default threshold chosen on the evaluated data (optimistic); motion re-wear cannot tell wear
from carrying; epoch statistics assume ≥ 20 Hz and noise ≥ ~1 mg; host cannot control the device; power state unknown;
no on-device low-power mode; wrist PPG unmeasured; CSV `step_counter_version = 2.0` is ambiguous without the sibling
`metadata.json`.

## 12. Outstanding risks

1. Firmware 5.0.0 has never been compiled for the target or flashed; profile B untested on a device.
2. If W1 shows LSM6DS3 table noise is not clearly below worn-still noise, the stillness criterion is useless and the extra
   sensor becomes mandatory (hardware change, Phase 12 enclosure).
3. Overnight recording is not validated; a 700 mAh pack (unverified) may not last a night in profile B (unmeasured).
4. Datasets PD@Home, MESA, WESAD, PPP have unconfirmed access/licence terms.
5. Board identity discrepancy (nRF52840 vs ESP32-S3 in photo).

## 13. Git commits

* `490b788` code, tests, benchmark, CI
* `c6e8dc4` documentation, registers, ADRs
* final-report commit (this file and `docs/PROJECT_STATE.md`), identified by `git log -- docs/audit/PHASE_8_FINAL_REPORT.md`

## 14. Exact reproduction commands

```bash
pip install -e ".[dev]"            # or the project's CI extras
pytest                              # bare, as CI runs it
flake8 parkinsense tests benchmarks --count --select=E9,F63,F7,F82,F401,F811,F841
python scripts/check_doc_links.py && npx markdownlint-cli2 "**/*.md"
g++ -std=c++17 -Wall -Wextra -Werror -I firmware/parkinsense_wearable firmware/tests/test_packet.cpp -o /tmp/t && /tmp/t
python -m benchmarks.external.fetch walch karas      # one dataset per argument if the CLI requires
python -m benchmarks.wear_bench --out benchmarks/results/wear_public_data.json
parkinsense-wear recordings/<session>/capture.csv --set still_acc_sd_g=0.001
```

## 15. Recommended next phase

Do **not** start Phase 9 as a pure algorithm exercise before two cheap, decisive hardware steps, which need a person with
the board: **W0** (identify the board) and **W1/W2** (bench noise and worn-still distribution with the existing board in
profile B), plus **H1–H3/H5** for firmware 5.0.0. They decide whether a sensor must be added. In parallel, Phase 9 can
begin on public data (tremor baseline against ParaDigMa on PD@Home once access is confirmed; Daphnet for FoG).
Mobile 2.0 (Phase 10) should wait for the wear states and `metadata_revision` to be final, and must display `inferred`
wear honestly.
