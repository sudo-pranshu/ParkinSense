# Project state (concise handover)

Updated 2026-11-15 (pipeline 3.1.0 checkpoint; Nov-14 work rebuilt after a sandbox loss, see below). Read this first; do not re-audit the repository.

**Cycle scope (owner, Nov–Dec 2026):** Phase 8 (continuous/wear-aware acquisition, firmware, BLE, power, physical
validation) then Phase 9 (public datasets, open-source algorithm research, benchmarking, improvements). Phases 10–13
(mobile, product UI, cloud, pilot) are deferred to December 2026 or later. A phase is complete only when its evidence and
acceptance criteria are met, not when code exists.

| Item | State |
|---|---|
| Branch / CI | `transform/engineering-overhaul` (not merged; `develop` untouched); see the test count in the checkpoint report (1 hardware test deselected by design) |
| Production algorithms | tremor v3 (PSD + HMM), steps v1.1 default, sleep 1.0 (offline), PPG 2.0 + noise gate (ADR-0017). Pipeline 3.1.0: IMU faults/missing samples → UNKNOWN (ADR-0015); API localhost + token (ADR-0016); biomarker sidecar 1.0.0 (ADR-0018). 10 s HRV is EXPLORATORY and unsummarised; SpO₂ never VALID |
| Experimental | gated step counter (opt-in, fails 2 of 7 criteria); wear monitor 1.0 (opt-in `--wear`, observe-only in the live runtime and dashboard, provisional thresholds) |
| Firmware | no firmware change in Phase 8. Owner reports (2026-11-06) the updated firmware, dashboard and system tested on themselves and working; no version/profile, IDs, durations, logs or measurements attached, so no documented test counts as run. v4 remains the last firmware with documented hardware verification |
| **Phase 8** | **Software, documentation and public-data evaluation done. NOT complete:** acceptance needs recorded hardware evidence (W0–W8, H1–H3, H5, PPK2 S1–S7): all documented tests NOT RUN; owner-reported informal testing noted; first session prepared: [checklist](validation/HARDWARE_SESSION_CHECKLIST.md) |
| Phase 9 | Task 1 prepared, not run: [tremor baseline plan](research/PHASE_9_TREMOR_BASELINE_PLAN.md) and [FoG plan](research/PHASE_9_FOG_PLAN.md) with pre-registered criteria; PD@Home access/licence unconfirmed (owner action), Daphnet to be downloaded by the owner. Research infrastructure: [dataset register](datasets/DATASET_REGISTER.md), [benchmark registry](validation/BENCHMARK_REGISTRY.md), [open-source review](research/OPEN_SOURCE_WEARABLE_REVIEW.md). No algorithm work started |

## Blocking the next milestones

1. **Hardware (needs the board and a person):** W0 board identity; W1/W2 bench and worn-still noise in profile B
   (`REQUIRE_FINGER_FOR_STREAMING = false`); H1–H3 for firmware 5.0.0; PPK2 S1–S7. Plan:
   [PHASE_8_VALIDATION_PLAN](validation/PHASE_8_VALIDATION_PLAN.md). W1/W2 decide whether an extra skin-contact sensor is required.
2. **Dataset access (Phase 9):** confirm PD@Home access/licence (Radboud), MESA terms (NSRR), WESAD licence, PPP request.
   The build environment reaches only GitHub and PyPI, so downloads from PhysioNet/UCI/NSRR/Radboud must be done
   elsewhere and placed under `data/external/`.

## Key decisions

ADR-0013 (step label corrected additively), ADR-0014 (wear inference on the host, no firmware/protocol change), ADR-0010–0012
(sleep, step versioning, gated counter opt-in). Wear default `still_acc_sd_g = 1 mg` is a fail-safe, provisional.

## Owner-approved 2026-11-15 and done in software

WP-07, WP-03, WP-09B (thresholds provisional, synthetic-derived; one real unlabelled recording lost its 16 `VALID` HR
windows, golden changed for that recording only), wear monitor exposure, sidecar/HRV policy. Overnight plan:
[OVERNIGHT_TEST_PROTOCOL](validation/OVERNIGHT_TEST_PROTOCOL.md) (not run). **Not rebuilt after the sandbox loss:**
tolerant capture reader, streaming replay, dataset manifest tool (the earlier 19 local commits were lost before push).

## Next actions, in order

1. Hardware: first session per the [checklist](validation/HARDWARE_SESSION_CHECKLIST.md) (W0, H0–H3/H9, W1, W2, PPK2 subset).
2. Phase 9: owner confirms PD@Home access/licence and downloads Daphnet; then ingestion manifest, ParaDigMa LOSO
   reproduction, ParkinSense v3 as-is and the Daphnet baseline, under the criteria already fixed in
   [tremor](research/PHASE_9_TREMOR_BASELINE_PLAN.md) and [FoG](research/PHASE_9_FOG_PLAN.md) plans.
3. Keep experimental code opt-in until criteria pass.

Details: [Phase 8 final report](audit/PHASE_8_FINAL_REPORT.md).
