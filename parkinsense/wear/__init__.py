"""Wear-state inference (Phase 8). See docs/architecture/WEAR_AWARE_ACQUISITION.md."""

from parkinsense.wear.monitor import (
    WEAR_MONITOR_VERSION,
    ImuState,
    LinkState,
    PowerState,
    PpgState,
    WearConfig,
    WearMonitor,
    WearState,
    WearStatus,
)

__all__ = ["WEAR_MONITOR_VERSION", "ImuState", "LinkState", "PowerState", "PpgState", "WearConfig",
           "WearMonitor", "WearState", "WearStatus", "analyze_arrays"]


def analyze_arrays(t, acc, gyro=None, ir=None, imu_ok=None, ppg_ok=None, config=None, fs=104.0,
                   chunk=1000, keep_epochs=True) -> WearMonitor:
    """Offline helper: run a whole recording through a fresh monitor and return it (flushed)."""
    import numpy as np
    cfg = config or WearConfig(expected_rate_hz=fs)
    m = WearMonitor(cfg, keep_epochs=keep_epochs)
    n = len(t)
    for i in range(0, n, chunk):
        sl = slice(i, i + chunk)
        m.update_block(np.asarray(t)[sl], np.asarray(acc)[sl], None if gyro is None else np.asarray(gyro)[sl],
                       None if ir is None else np.asarray(ir)[sl],
                       None if imu_ok is None else np.asarray(imu_ok)[sl],
                       None if ppg_ok is None else np.asarray(ppg_ok)[sl])
    m.flush()
    return m
