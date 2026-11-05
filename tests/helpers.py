import numpy as np

from parkinsense.protocol.packet import BATCH_SIZE, SAMPLE_PERIOD_US, encode


def packets(imu, ir=None, red=None, version=1, t0_us=1_000_000, seq0=0):
    ir = np.full(imu.n, 1600) if ir is None else ir
    red = np.full(imu.n, 600) if red is None else red
    n = (imu.n // BATCH_SIZE) * BATCH_SIZE
    for p, start in enumerate(range(0, n, BATCH_SIZE)):
        rows = [(imu.ax[i], imu.ay[i], imu.az[i], imu.gx[i], imu.gy[i], imu.gz[i], int(ir[i]), int(red[i]))
                for i in range(start, start + BATCH_SIZE)]
        yield encode(rows, t0_us + start * SAMPLE_PERIOD_US, version=version, seq=seq0 + p)


def run_engine(engine, imu, **kw):
    rows, analyses = [], []
    for data in packets(imu, **kw):
        r = engine.process_packet(data, host_monotonic=0.0, host_wall=0.0)
        rows += r.rows
        analyses += r.analyses
    return rows, analyses




NIGHT_FS = 50.0


def synthetic_night(hours_still=6.0, wake_before_min=20, wake_after_min=20, seed=0):
    """Gravity-aligned wrist: lively -> motionless (with rare twitches) -> lively."""
    rng = np.random.default_rng(seed)
    parts = []
    for minutes, active in ((wake_before_min, True), (hours_still * 60, False), (wake_after_min, True)):
        n = int(minutes * 60 * NIGHT_FS)
        a = np.tile([0.0, 0.0, 1.0], (n, 1)) + rng.normal(0, 0.004, (n, 3))
        if not active:                             # sleepers twitch / turn: a burst every ~2-4 min
            k = 0
            while k < n - 10 * int(NIGHT_FS):
                k += int(rng.uniform(120, 240) * NIGHT_FS)
                m = int(rng.uniform(1, 3) * NIGHT_FS)
                a[k:k + m, 0] += rng.uniform(0.05, 0.15)
        if active:                                 # awake: the arm keeps changing orientation (new pose every 3 s)
            seg = int(3 * NIGHT_FS)
            th = rng.uniform(0, np.pi / 2, n // seg + 1)
            ph = rng.uniform(0, 2 * np.pi, n // seg + 1)
            g = np.stack([np.sin(th) * np.cos(ph), np.sin(th) * np.sin(ph), np.cos(th)], 1)
            a = np.repeat(g, seg, axis=0)[:n] + rng.normal(0, 0.05, (n, 3))
        parts.append(a)
    acc = np.vstack(parts)
    return np.arange(len(acc)) / NIGHT_FS, acc


