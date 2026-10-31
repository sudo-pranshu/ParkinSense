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


