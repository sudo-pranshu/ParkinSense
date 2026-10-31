"""
Personal baselines and deviation detection (conservative by design).

A baseline is a robust summary (median, MAD) of one daily metric over a
rolling history of *qualifying* days. A new day is compared as a robust
z-score  z = (x - median) / (1.4826 * MAD).

Safeguards against "silently adapting to bad measurements":
  * a day only enters the baseline if it meets the metric's minimum valid
    observation time (e.g. >= 10 min of still, valid tremor windows);
  * no deviation is reported until MIN_DAYS qualifying days exist;
  * a day flagged by provenance checks (firmware/pipeline version change,
    rate_status != OK, packet loss above threshold) does not enter the
    baseline and its deviation is reported as NOT_COMPARABLE -- a change of
    hardware or algorithm is not a change in the person;
  * the baseline is frozen (not updated) on days that deviate by more than
    FREEZE_Z, so an acute change cannot drag the reference toward itself.

This flags *change relative to the individual*, nothing more. It is not a
clinical alert and carries no diagnostic meaning.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

MIN_DAYS = 7
WINDOW_DAYS = 28
DEVIATION_Z = 3.0
FREEZE_Z = 3.0
MAX_LOSS_FRACTION = 0.05


@dataclass
class DayRecord:
    day: str
    value: float | None
    qualifying: bool
    provenance: dict = field(default_factory=dict)


@dataclass
class PersonalBaseline:
    metric: str
    history: list = field(default_factory=list)
    reference_provenance: dict | None = None

    def _comparable(self, prov: dict) -> tuple[bool, str]:
        if prov.get("rate_status") not in (None, "OK"):
            return False, f"rate_status={prov.get('rate_status')}"
        if (prov.get("loss_fraction") or 0) > MAX_LOSS_FRACTION:
            return False, "packet loss above threshold"
        if self.reference_provenance:
            for k in ("pipeline_version", "firmware_version"):
                if prov.get(k) and self.reference_provenance.get(k) and prov[k] != self.reference_provenance[k]:
                    return False, f"{k} changed ({self.reference_provenance[k]} -> {prov[k]})"
        return True, ""

    def stats(self):
        vals = [d.value for d in self.history[-WINDOW_DAYS:] if d.qualifying and d.value is not None]
        if len(vals) < MIN_DAYS:
            return None
        med = float(np.median(vals))
        mad = float(np.median(np.abs(np.array(vals) - med)))
        return {"median": med, "mad": mad, "n_days": len(vals)}

    def add_day(self, rec: DayRecord) -> dict:
        ok, why = self._comparable(rec.provenance)
        if not ok:
            return {"day": rec.day, "status": "NOT_COMPARABLE", "reason": why}
        if not rec.qualifying or rec.value is None:
            return {"day": rec.day, "status": "INSUFFICIENT_DATA"}
        st = self.stats()
        if st is None:
            self._append(rec)
            return {"day": rec.day, "status": "BUILDING_BASELINE",
                    "qualifying_days": sum(d.qualifying for d in self.history)}
        scale = 1.4826 * st["mad"]
        z = (rec.value - st["median"]) / scale if scale > 0 else 0.0
        status = "DEVIATION" if abs(z) >= DEVIATION_Z else "WITHIN_BASELINE"
        if abs(z) < FREEZE_Z:
            self._append(rec)
        return {"day": rec.day, "status": status, "z": round(z, 2), "baseline": st}

    def _append(self, rec):
        if self.reference_provenance is None:
            self.reference_provenance = {k: rec.provenance.get(k) for k in ("pipeline_version", "firmware_version")}
        self.history.append(rec)
