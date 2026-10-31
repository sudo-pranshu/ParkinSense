"""
Session / day-level digital biomarkers from window-level outputs.

Input: analysis rows (`is_analysis_row == True`) from a capture or the
dataset builder. Every aggregate reports how much *valid* observation time it
rests on; aggregates over too little valid data are returned as None with a
reason instead of a number.

Tremor aggregates follow the ParaDigMa definitions (Timmermans et al.,
npj Parkinson's Dis 2025), adapted to our 0.5 s hop:
  tremor_time_pct   = windows with detected rest tremor / windows without
                      purposeful arm movement (REST + LOW MOTION), x 100;
  tremor_power      = median, modal and 90th-percentile of log10(P_T + 1)
                      over tremor windows, only reported when
                      tremor_time_pct >= 3.5 % (their threshold);
  tremor frequency  = median of detected windows' peak frequency.
Windows are time-weighted by the hop, so overlap does not bias percentages.

Not provided, deliberately: bradykinesia, dyskinesia, freezing-of-gait and
sleep scores. Each needs validated reference data this project does not have
(see docs/research/BIOMARKER_FEASIBILITY.md). PKG/Kinesia-style scores are
proprietary and their algorithms are not public.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from parkinsense.config import ANALYSIS_HOP_SECONDS

MIN_VALID_MINUTES = 10.0
TREMOR_POWER_MIN_TIME_PCT = 3.5


def _analysis_rows(df: pd.DataFrame) -> pd.DataFrame:
    if "is_analysis_row" in df.columns:
        df = df[df["is_analysis_row"].astype(str).str.lower().isin(["true", "1"])]
    return df


def tremor_summary(df: pd.DataFrame, min_valid_minutes=MIN_VALID_MINUTES) -> dict:
    a = _analysis_rows(df)
    valid = a[a["tremor_quality"].isin(["VALID", "LOW_CONFIDENCE"])] if "tremor_quality" in a else a
    still = valid[valid["motion_state"].isin(["REST", "LOW MOTION"])]
    minutes = len(still) * ANALYSIS_HOP_SECONDS / 60.0
    out = {"still_minutes": round(minutes, 2), "valid_windows": int(len(valid))}
    if minutes < min_valid_minutes:
        return {**out, "tremor_time_pct": None,
                "reason": f"only {minutes:.1f} min of still, valid data (< {min_valid_minutes})"}
    trem = still[(still["classification"] == "TREMOR") & (still["tremor_type"] == "REST")]
    pct = 100.0 * len(trem) / len(still)
    out["tremor_time_pct"] = round(pct, 2)
    det = trem[trem.get("tremor_evidence", pd.Series(1.0, index=trem.index)) >= 0.5]
    out["tremor_frequency_hz_median"] = float(det["dominant_frequency"].median()) if len(det) else None
    if pct >= TREMOR_POWER_MIN_TIME_PCT and len(det):
        lp = np.log10(det["tremor_power"].astype(float) + 1.0)
        hist, edges = np.histogram(lp, bins=20)
        out.update({
            "tremor_power_median": round(float(lp.median()), 4),
            "tremor_power_modal": round(float((edges[hist.argmax()] + edges[hist.argmax() + 1]) / 2), 4),
            "tremor_power_p90": round(float(lp.quantile(0.9)), 4),
            "tremor_amplitude_dps_median": round(float(det["tremor_amplitude_dps"].median()), 3),
        })
    else:
        out["tremor_power_median"] = None
        out["tremor_power_note"] = f"tremor time < {TREMOR_POWER_MIN_TIME_PCT}% -- power not reported"
    return out


def heart_summary(df: pd.DataFrame, min_valid_minutes=2.0) -> dict:
    a = _analysis_rows(df)
    v = a[a["hr_quality_state"] == "VALID"] if "hr_quality_state" in a else a.iloc[0:0]
    minutes = len(v) * ANALYSIS_HOP_SECONDS / 60.0
    if minutes < min_valid_minutes:
        return {"valid_minutes": round(minutes, 2), "hr_median": None,
                "reason": "insufficient VALID heart-rate windows"}
    rest = v[v["motion_state"] == "REST"]
    return {
        "valid_minutes": round(minutes, 2),
        "hr_median": float(v["heart_rate"].median()),
        "hr_rest_p10": float(rest["heart_rate"].quantile(0.1)) if len(rest) >= 20 else None,
        "rmssd_median": float(v["rmssd"].dropna().median()) if v["rmssd"].notna().any() else None,
        "coverage_pct": round(100 * len(v) / max(len(a), 1), 1),
    }


def activity_summary(df: pd.DataFrame) -> dict:
    a = _analysis_rows(df)
    steps = a["steps"].dropna()
    walk = a[a.get("walking_state", pd.Series(dtype=str)) == "WALKING"] if "walking_state" in a else a.iloc[0:0]
    return {
        "steps": int(steps.iloc[-1]) if len(steps) else None,
        "walking_minutes": round(len(walk) * ANALYSIS_HOP_SECONDS / 60.0, 2),
        "cadence_median_spm": float(walk["cadence"].median()) if len(walk) else None,
        "active_fraction": round(float((a["motion_state"] == "ACTIVE").mean()), 4) if len(a) else None,
    }


def session_report(df: pd.DataFrame) -> dict:
    return {"tremor": tremor_summary(df), "heart": heart_summary(df), "activity": activity_summary(df)}
