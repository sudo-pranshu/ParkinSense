"""
Synthetic wrist-sensor signals with exact ground truth.

Purpose
-------
Deterministic (seeded) test and benchmark material for the motion, tremor,
activity and PPG pipelines. Every generator returns the signal *and* the
quantity it was built from (tremor frequency/amplitude, true step count,
true beat times / RR series, true ratio-of-ratios R).

What this is NOT
----------------
Synthetic signals verify that an algorithm recovers a *known, idealised*
quantity. They cannot establish clinical accuracy, and results on them must
never be reported as such. Parameter ranges are chosen from published
descriptions (cited inline) so the tests are not trivially easy, but they are
models, not recordings.

Conventions: gyroscope in deg/s, accelerometer in g, PPG in raw 18-bit ADC
counts, all sampled on a uniform grid at ``fs`` Hz.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
from scipy.signal import butter, sosfiltfilt

DEFAULT_FS = 104.0

# Lever arm from forearm rotation axis to a wrist-worn sensor (m). Converts
# angular acceleration into tangential linear acceleration.
WRIST_LEVER_M = 0.07
G = 9.80665


@dataclass
class ImuSignal:
    fs: float
    ax: np.ndarray
    ay: np.ndarray
    az: np.ndarray
    gx: np.ndarray
    gy: np.ndarray
    gz: np.ndarray
    # Ground truth -----------------------------------------------------------
    label: str = "unknown"
    tremor_present: bool = False
    tremor_freq_hz: float | None = None
    tremor_amp_dps: float | None = None   # peak angular velocity of the tremor
    voluntary_movement: bool = False
    true_steps: int = 0
    meta: dict = field(default_factory=dict)

    @property
    def n(self) -> int:
        return len(self.gx)

    def gyro(self) -> np.ndarray:
        return np.vstack([self.gx, self.gy, self.gz])

    def accel(self) -> np.ndarray:
        return np.vstack([self.ax, self.ay, self.az])


def _bandlimited_noise(rng, n, fs, lo, hi, rms):
    """Zero-mean Gaussian noise band-limited to [lo, hi] Hz, scaled to `rms`."""
    x = rng.standard_normal(n + 512)
    nyq = fs / 2
    if lo <= 0:
        sos = butter(4, hi / nyq, btype="low", output="sos")
    else:
        sos = butter(4, [lo / nyq, hi / nyq], btype="band", output="sos")
    y = sosfiltfilt(sos, x)[256:-256]
    s = np.std(y)
    return y * (rms / s) if s > 0 else y


def _random_unit(rng, dominant: int | None = None, dominance: float = 0.8):
    v = rng.standard_normal(3)
    v /= np.linalg.norm(v)
    if dominant is not None:
        e = np.zeros(3)
        e[dominant] = 1.0 if rng.random() < 0.5 else -1.0
        v = dominance * e + (1 - dominance) * v
        v /= np.linalg.norm(v)
    return v


def _rotate_gravity(gyro_dps: np.ndarray, fs: float, g0: np.ndarray) -> np.ndarray:
    """
    Gravity vector in the sensor frame as the sensor rotates with angular
    velocity `gyro_dps` (3 x n). First-order quaternion-free integration
    (Rodrigues per step) -- accurate enough for test signals.
    """
    n = gyro_dps.shape[1]
    out = np.empty((3, n))
    g = g0.astype(float).copy()
    dt = 1.0 / fs
    w = np.deg2rad(gyro_dps)
    for i in range(n):
        out[:, i] = g
        wi = w[:, i]
        th = np.linalg.norm(wi) * dt
        if th > 0:
            k = wi / np.linalg.norm(wi)
            # world is fixed, sensor rotates by +th -> vector rotates by -th
            g = (g * np.cos(-th) + np.cross(k, g) * np.sin(-th)
                 + k * np.dot(k, g) * (1 - np.cos(-th)))
    return out


def _assemble(rng, fs, gyro, extra_lin_acc_g=None, g0=None,
              gyro_noise_dps=0.35, acc_noise_g=0.003):
    n = gyro.shape[1]
    if g0 is None:
        g0 = np.array([0.05, -0.15, -0.98])
        g0 /= np.linalg.norm(g0)
    grav = _rotate_gravity(gyro, fs, g0)
    # tangential acceleration from angular acceleration about a lever arm
    alpha = np.gradient(np.deg2rad(gyro), 1.0 / fs, axis=1)       # rad/s^2
    lever = np.array([0.0, WRIST_LEVER_M, 0.0])
    tang = np.cross(alpha.T, lever).T / G                           # g
    acc = grav + tang
    if extra_lin_acc_g is not None:
        acc = acc + extra_lin_acc_g
    acc = acc + rng.normal(0, acc_noise_g, size=acc.shape)
    gyr = gyro + rng.normal(0, gyro_noise_dps, size=gyro.shape)
    # slow gyro bias wander (MEMS) -- irrelevant to band-limited analysis but realistic
    gyr = gyr + _bandlimited_noise(rng, n, fs, 0, 0.05, 0.4)[None, :]
    return acc, gyr


def _tremor_component(rng, n, fs, f0, amp, fm_dev=0.15, am_depth=0.25):
    """Quasi-periodic tremor: slow FM (+-fm_dev Hz) and AM (depth am_depth)."""
    t = np.arange(n) / fs
    fm = f0 + _bandlimited_noise(rng, n, fs, 0, 0.3, fm_dev)
    phase = 2 * np.pi * np.cumsum(fm) / fs + rng.uniform(0, 2 * np.pi)
    am = 1.0 + am_depth * _bandlimited_noise(rng, n, fs, 0, 0.2, 0.6)
    am = np.clip(am, 0.2, None)
    return amp * am * np.sin(phase) + 0 * t


def rest(fs=DEFAULT_FS, seconds=30.0, seed=0, micro_rms=1.0) -> ImuSignal:
    """Arm at rest: sensor noise + low-amplitude postural micro-motion."""
    rng = np.random.default_rng(seed)
    n = int(seconds * fs)
    gyro = np.vstack([_bandlimited_noise(rng, n, fs, 0.1, 2.0, micro_rms) for _ in range(3)])
    acc, gyr = _assemble(rng, fs, gyro)
    return ImuSignal(fs, *acc, *gyr, label="rest")


def rest_tremor(fs=DEFAULT_FS, seconds=30.0, seed=0, freq=None, amp=None,
                dominant_axis=None) -> ImuSignal:
    """
    Parkinsonian rest tremor: 3.5-7 Hz (typical 4-6 Hz; Deuschl et al.,
    Mov Disord 1998 consensus), quasi-sinusoidal, predominantly about one
    forearm axis (pronation/supination).
    """
    rng = np.random.default_rng(seed)
    n = int(seconds * fs)
    f0 = float(freq if freq is not None else rng.uniform(4.0, 6.5))
    a = float(amp if amp is not None else np.exp(rng.uniform(np.log(8), np.log(120))))
    ax_idx = dominant_axis if dominant_axis is not None else int(rng.integers(0, 3))
    u = _random_unit(rng, ax_idx, 0.85)
    trem = _tremor_component(rng, n, fs, f0, a)
    micro = np.vstack([_bandlimited_noise(rng, n, fs, 0.1, 2.0, 1.0) for _ in range(3)])
    gyro = u[:, None] * trem[None, :] + micro
    acc, gyr = _assemble(rng, fs, gyro)
    return ImuSignal(fs, *acc, *gyr, label="rest_tremor", tremor_present=True,
                     tremor_freq_hz=f0, tremor_amp_dps=a, meta={"axis": ax_idx})


def voluntary(fs=DEFAULT_FS, seconds=30.0, seed=0, rms=None) -> ImuSignal:
    """Purposeful arm movement: smooth, broadband 0.2-3 Hz rotations."""
    rng = np.random.default_rng(seed)
    n = int(seconds * fs)
    r = float(rms if rms is not None else rng.uniform(25, 140))
    gyro = np.vstack([_bandlimited_noise(rng, n, fs, 0.2, 3.0, r * w)
                      for w in (1.0, 0.7, 0.5)])
    gyro = gyro[rng.permutation(3)]
    acc, gyr = _assemble(rng, fs, gyro)
    return ImuSignal(fs, *acc, *gyr, label="voluntary", voluntary_movement=True,
                     meta={"rms_dps": r})


def walking(fs=DEFAULT_FS, seconds=30.0, seed=0, cadence_spm=None,
            swing_dps=None) -> ImuSignal:
    """
    Walking with arm swing modelled as a shoulder pendulum (r = 0.6 m):
    arm angle theta(t) oscillates at the stride frequency (cadence/120 Hz).
    The wrist's specific force is computed in the world frame (tangential
    r*theta'' at stride frequency, centripetal r*theta'^2 at *step* frequency,
    vertical heel-strike impacts at step frequency) and rotated into the
    sensor frame, so |a| has the physically correct step-frequency content.
    Ground truth step count = cadence * duration.
    """
    rng = np.random.default_rng(seed)
    n = int(seconds * fs)
    cad = float(cadence_spm if cadence_spm is not None else rng.uniform(90, 120))
    f_step = cad / 60.0
    f_stride = f_step / 2.0
    sw = float(swing_dps if swing_dps is not None else rng.uniform(50, 140))
    r = 0.6
    jitter = _bandlimited_noise(rng, n, fs, 0, 0.2, 0.02 * f_stride)
    ph = 2 * np.pi * np.cumsum(f_stride + jitter) / fs + rng.uniform(0, 2 * np.pi)
    w_max = np.deg2rad(sw)
    theta = (w_max / (2 * np.pi * f_stride)) * np.sin(ph) + 0.05 * np.sin(2 * ph + 0.3)
    thd = np.gradient(theta, 1 / fs)
    thdd = np.gradient(thd, 1 / fs)
    # wrist position (x fwd, z up) and its acceleration, in m/s^2
    ax_w = r * (thdd * np.cos(theta) - thd ** 2 * np.sin(theta))
    az_w = r * (thdd * np.sin(theta) + thd ** 2 * np.cos(theta))
    impact = np.maximum(0, np.cos(2 * ph)) ** 6 * rng.uniform(0.15, 0.35) * G
    az_w = az_w + impact
    fx, fz = ax_w, az_w + G                       # specific force, world frame
    # rotate into sensor frame (rotation by theta about y)
    sx = (fx * np.cos(theta) + fz * np.sin(theta)) / G
    sz = (-fx * np.sin(theta) + fz * np.cos(theta)) / G
    sy = 0.03 * _bandlimited_noise(rng, n, fs, 0.2, 4.0, 1.0)
    gyro = np.vstack([np.zeros(n), np.rad2deg(thd), np.zeros(n)])
    gyro += np.vstack([_bandlimited_noise(rng, n, fs, 0.1, 4.0, 4.0) for _ in range(3)])
    acc = np.vstack([sx, sy, sz]) + rng.normal(0, 0.003, size=(3, n))
    gyr = gyro + rng.normal(0, 0.35, size=gyro.shape)
    # random fixed mounting orientation of the device on the wrist
    q = rng.standard_normal(3); q /= np.linalg.norm(q)
    ang = rng.uniform(0, 0.4)
    K = np.array([[0, -q[2], q[1]], [q[2], 0, -q[0]], [-q[1], q[0], 0]])
    R = np.eye(3) + np.sin(ang) * K + (1 - np.cos(ang)) * K @ K
    acc, gyr = R @ acc, R @ gyr
    steps = int(round(cad * seconds / 60.0))
    return ImuSignal(fs, *acc, *gyr, label="walking", voluntary_movement=True,
                     true_steps=steps, meta={"cadence_spm": cad, "swing_dps": sw})


def walking_with_tremor(fs=DEFAULT_FS, seconds=30.0, seed=0) -> ImuSignal:
    w = walking(fs, seconds, seed)
    tr = rest_tremor(fs, seconds, seed + 10_000, amp=40.0)
    gy = w.gyro() + (tr.gyro() - rest(fs, seconds, seed + 10_000).gyro())
    out = ImuSignal(fs, w.ax, w.ay, w.az, *gy, label="walking_with_tremor",
                    tremor_present=True, tremor_freq_hz=tr.tremor_freq_hz,
                    tremor_amp_dps=40.0, voluntary_movement=True,
                    true_steps=w.true_steps)
    return out


def vibration(fs=DEFAULT_FS, seconds=30.0, seed=0) -> ImuSignal:
    """External vibration (vehicle/appliance), 12-25 Hz, no tremor."""
    rng = np.random.default_rng(seed)
    n = int(seconds * fs)
    f = rng.uniform(12, 25)
    t = np.arange(n) / fs
    vib = np.sin(2 * np.pi * f * t)
    gyro = np.vstack([_bandlimited_noise(rng, n, fs, 0.1, 2.0, 1.0) for _ in range(3)])
    gyro += np.outer(_random_unit(rng), 4.0 * vib)
    lin = np.outer(_random_unit(rng), 0.06 * vib)
    acc, gyr = _assemble(rng, fs, gyro, extra_lin_acc_g=lin)
    return ImuSignal(fs, *acc, *gyr, label="vibration", meta={"freq_hz": f})


def non_pd_oscillation(fs=DEFAULT_FS, seconds=30.0, seed=0) -> ImuSignal:
    """8.5-11 Hz oscillation (e.g. enhanced physiological tremor): outside the PD rest-tremor band."""
    rng = np.random.default_rng(seed)
    s = rest_tremor(fs, seconds, seed, freq=rng.uniform(8.5, 11.0), amp=rng.uniform(15, 40))
    s.label = "non_pd_oscillation"
    s.tremor_present = False
    return s


def subtle_tremor(fs=DEFAULT_FS, seconds=30.0, seed=0) -> ImuSignal:
    rng = np.random.default_rng(seed + 555)
    s = rest_tremor(fs, seconds, seed, amp=float(rng.uniform(3, 8)))
    s.label = "subtle_tremor"
    return s


def strong_tremor(fs=DEFAULT_FS, seconds=30.0, seed=0) -> ImuSignal:
    rng = np.random.default_rng(seed + 777)
    s = rest_tremor(fs, seconds, seed, amp=float(rng.uniform(120, 240)))
    s.label = "strong_tremor"
    return s


def action_tremor(fs=DEFAULT_FS, seconds=30.0, seed=0) -> ImuSignal:
    """Tremor superimposed on purposeful movement (re-emergent/action tremor)."""
    v = voluntary(fs, seconds, seed, rms=60.0)
    t = rest_tremor(fs, seconds, seed + 4242, amp=40.0)
    base = rest(fs, seconds, seed + 4242)
    g = v.gyro() + (t.gyro() - base.gyro())
    return ImuSignal(fs, v.ax + (t.ax - base.ax), v.ay + (t.ay - base.ay), v.az + (t.az - base.az),
                     *g, label="action_tremor", tremor_present=True,
                     tremor_freq_hz=t.tremor_freq_hz, tremor_amp_dps=40.0, voluntary_movement=True)


SCENARIOS = {
    "rest": rest,
    "rest_tremor": rest_tremor,
    "voluntary": voluntary,
    "walking": walking,
    "walking_with_tremor": walking_with_tremor,
    "vibration": vibration,
    "non_pd_oscillation": non_pd_oscillation,
    "subtle_tremor": subtle_tremor,
    "strong_tremor": strong_tremor,
    "action_tremor": action_tremor,
}


def concatenate(segments: list[ImuSignal]) -> tuple[ImuSignal, np.ndarray]:
    """Join segments; returns the signal and a per-sample tremor ground-truth mask."""
    fs = segments[0].fs
    cat = {k: np.concatenate([getattr(s, k) for s in segments])
           for k in ("ax", "ay", "az", "gx", "gy", "gz")}
    mask = np.concatenate([np.full(s.n, s.tremor_present) for s in segments])
    out = ImuSignal(fs, **cat, label="+".join(s.label for s in segments),
                    true_steps=sum(s.true_steps for s in segments))
    return out, mask


# ---------------------------------------------------------------------------
# PPG
# ---------------------------------------------------------------------------

@dataclass
class PpgSignal:
    fs: float
    ir: np.ndarray
    red: np.ndarray
    beat_times_s: np.ndarray
    rr_ms: np.ndarray
    true_hr_bpm: float
    true_rmssd_ms: float
    true_sdnn_ms: float
    true_r: float           # (AC_red/DC_red)/(AC_ir/DC_ir)
    label: str = "ppg"


def _rr_series(rng, seconds, hr_bpm, rmssd_ms, resp_hz=0.25):
    """
    RR tachogram: mean 60/hr, respiratory sinus arrhythmia at resp_hz plus
    white beat-to-beat variability scaled so RMSSD ~= rmssd_ms.
    """
    mean_rr = 60.0 / hr_bpm
    rr = []
    t = 0.0
    while t < seconds + 2:
        rsa = 0.5 * rmssd_ms / 1000.0 * np.sin(2 * np.pi * resp_hz * t)
        v = mean_rr + rsa + rng.normal(0, rmssd_ms / 1000.0 / np.sqrt(2))
        v = float(np.clip(v, 0.3, 2.0))
        rr.append(v)
        t += v
    return np.array(rr)


def ppg(fs=100.0, seconds=60.0, seed=0, hr_bpm=None, rmssd_ms=None,
        perfusion=0.015, r_ratio=0.6, noise=0.04, motion_g=None,
        motion_freq_hz=None, dc_ir=110_000.0, dc_red=85_000.0) -> PpgSignal:
    """
    Two-Gaussian pulse model (systolic + diastolic wave; cf. Charlton et al.,
    Physiol Meas 2022 for pulse-wave morphology), respiratory baseline
    wander, white noise, and optional periodic motion artefact.

    Returns raw ADC counts as the MAX30102 would report them at `fs`.
    """
    rng = np.random.default_rng(seed)
    hr = float(hr_bpm if hr_bpm is not None else rng.uniform(55, 100))
    rm = float(rmssd_ms if rmssd_ms is not None else rng.uniform(15, 60))
    rr = _rr_series(rng, seconds, hr, rm)
    beats = np.cumsum(rr) - rr[0] + rng.uniform(0, rr[0])
    beats = beats[beats < seconds]
    n = int(seconds * fs)
    t = np.arange(n) / fs
    pulse = np.zeros(n)
    for i, tb in enumerate(beats):
        p = rr[min(i, len(rr) - 1)]
        pulse += np.exp(-0.5 * ((t - (tb + 0.0)) / (0.12 * p)) ** 2)
        pulse += 0.45 * np.exp(-0.5 * ((t - (tb + 0.38 * p)) / (0.16 * p)) ** 2)
    pulse /= max(pulse.max(), 1e-9)
    pulse -= pulse.mean()
    resp = 0.3 * np.sin(2 * np.pi * 0.25 * t + rng.uniform(0, 6.28))
    shape = pulse + resp
    ac_ir = perfusion * dc_ir
    ac_red = r_ratio * perfusion * dc_red
    # Transmission dips with blood volume -> invert pulse in raw counts.
    ir = dc_ir - ac_ir * shape + rng.normal(0, noise * ac_ir, n)
    red = dc_red - ac_red * shape + rng.normal(0, noise * ac_red, n)
    if motion_g is not None:
        f = motion_freq_hz if motion_freq_hz is not None else 1.8
        art = motion_g * np.sign(np.sin(2 * np.pi * f * t)) * np.abs(np.sin(2 * np.pi * f * t)) ** 3
        ir += 40 * ac_ir * art
        red += 40 * ac_red * art
    rr_ms = np.diff(beats) * 1000.0
    d = np.diff(rr_ms)
    return PpgSignal(fs, ir, red, beats, rr_ms, true_hr_bpm=60000.0 / rr_ms.mean(),
                     true_rmssd_ms=float(np.sqrt(np.mean(d ** 2))),
                     true_sdnn_ms=float(np.std(rr_ms, ddof=1)), true_r=r_ratio)


def ppg_to_slots(sig: PpgSignal, slot_fs=DEFAULT_FS, path="v2") -> tuple[np.ndarray, np.ndarray]:
    """
    Reproduce what the host receives in each 104 Hz IMU slot.

    path="v1": legacy firmware (<= v4) -- PPG decimated to 10 Hz by keeping the
               newest FIFO sample (no anti-alias), zero-order-held into slots.
    path="v2": protocol-v2 firmware -- every FIFO sample delivered; slots carry
               the most recent (~100 Hz) sample.
    """
    n_slots = int(len(sig.ir) / sig.fs * slot_fs)
    ts = np.arange(n_slots) / slot_fs
    if path == "v1":
        src_t = np.arange(0, ts[-1] + 0.1, 0.1)
        idx = np.minimum((src_t * sig.fs).astype(int), len(sig.ir) - 1)
        ir_s, red_s = sig.ir[idx], sig.red[idx]
        k = np.minimum((ts / 0.1).astype(int), len(ir_s) - 1)
        return ir_s[k].astype(np.int64), red_s[k].astype(np.int64)
    idx = np.minimum((ts * sig.fs).astype(int), len(sig.ir) - 1)
    return sig.ir[idx].astype(np.int64), sig.red[idx].astype(np.int64)
