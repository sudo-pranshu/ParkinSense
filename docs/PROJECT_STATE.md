# Project state (concise handover)

Updated 2026-11-06 after Phase 8 software work. Read this first; do not re-audit the repository.

**Cycle scope (owner, Nov–Dec 2026):** Phase 8 (continuous/wear-aware acquisition, firmware, BLE, power, physical
validation) then Phase 9 (public datasets, open-source algorithm research, benchmarking, improvements). Phases 10–13
(mobile, product UI, cloud, pilot) are deferred to December 2026 or later. A phase is complete only when its evidence and
acceptance criteria are met, not when code exists.

| Item | State |
|---|---|
| Branch / CI | `transform/engineering-overhaul`; 139 tests pass locally (1 hardware test deselected by design) |
| Production algorithms | tremor v3 (PSD + HMM), steps v1.1 default, sleep 1.0 (offline), PPG 2.0 — unchanged |
| Experimental | gated step counter (opt-in, fails 2 of 7 criteria); wear monitor 1.0 (opt-in, provisional thresholds) |
| Firmware | 5.0.0 never compiled for target, flashed or measured; v4 is last hardware-verified; **no firmware change in Phase 8** |
| **Phase 8** | **Software, documentation and public-data evaluation done. NOT complete:** acceptance needs hardware evidence (W0–W8, H1–H3, H5, PPK2 S1–S7), all NOT RUN |
| Phase 9 | Research infrastructure only so far: [dataset register](datasets/DATASET_REGISTER.md), [benchmark registry](validation/BENCHMARK_REGISTRY.md), [open-source review](research/OPEN_SOURCE_WEARABLE_REVIEW.md). No algorithm work started |

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

## Next actions, in order

1. Hardware: W0, W1, W2, W5, H1–H3 (one session with the board).
2. Phase 9 start: tremor baseline vs ParaDigMa (Apache-2.0) on PD@Home once access is confirmed, with acceptance criteria
   written **before** any held-out run; FoG baseline on Daphnet (CC BY 4.0, open).
3. Keep experimental code opt-in until criteria pass.

Details: [Phase 8 final report](audit/PHASE_8_FINAL_REPORT.md).
