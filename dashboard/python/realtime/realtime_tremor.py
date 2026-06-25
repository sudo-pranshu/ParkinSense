import numpy as np

from collections import deque
from scipy.fft import rfft, rfftfreq


class RealtimeTremorDetector:

    def __init__(
        self,
        sample_rate=104,
        window_seconds=5
    ):

        self.sample_rate = sample_rate

        self.window_size = int(
            sample_rate *
            window_seconds
        )

        self.ax_buffer = deque(
            maxlen=self.window_size
        )

        self.ay_buffer = deque(
            maxlen=self.window_size
        )

        self.az_buffer = deque(
            maxlen=self.window_size
        )

        self.gx_buffer = deque(
            maxlen=self.window_size
        )

        self.gy_buffer = deque(
            maxlen=self.window_size
        )

        self.gz_buffer = deque(
            maxlen=self.window_size
        )

        self.freq_history = deque(
            maxlen=5
        )

        self.persistence = 0

        self.total_windows = 0
        self.tremor_windows = 0

    def add_sample(
        self,
        ax,
        ay,
        az,
        gx,
        gy,
        gz
    ):

        self.ax_buffer.append(ax)
        self.ay_buffer.append(ay)
        self.az_buffer.append(az)

        self.gx_buffer.append(gx)
        self.gy_buffer.append(gy)
        self.gz_buffer.append(gz)

    def ready(self):

        return (
            len(self.gx_buffer)
            >= self.window_size
        )

    def analyze(self):

        if not self.ready():
            return None

        ax = np.array(
            self.ax_buffer
        )
        ay = np.array(
            self.ay_buffer
        )
        az = np.array(
            self.az_buffer
        )

        gx = np.array(
            self.gx_buffer
        )

        gy = np.array(
            self.gy_buffer
        )

        gz = np.array(
            self.gz_buffer
        )

        acc_mag = np.sqrt(
            ax**2 +
            ay**2 +
            az**2
        )

        rest_index = np.std(acc_mag)

        gyro_mag = np.sqrt(
            gx**2 +
            gy**2 +
            gz**2
        )

        gyro_mag = (
            gyro_mag -
            np.mean(gyro_mag)
        )

        dominant_freqs = []
        energy_ratios = []

        segment = gyro_mag

        fft_vals = np.abs(
            rfft(segment)
        )

        freqs = rfftfreq(
            len(segment),
            d=1/self.sample_rate
        )

        band_mask = (
            (freqs >= 3.0) &
            (freqs <= 9.0)
        )

        band_freqs = freqs[
            band_mask
        ]

        band_fft = fft_vals[
            band_mask
        ]

        if len(band_fft) > 0:

            dominant_freqs.append(
                band_freqs[
                    np.argmax(
                        band_fft
                    )
                ]
            )

            total_energy = np.sum(
                fft_vals ** 2
            )

            band_energy = np.sum(
                band_fft ** 2
            )

            if total_energy > 0:

                energy_ratios.append(
                    band_energy /
                    total_energy
                )

        rms_motion = np.sqrt(
            np.mean(
                gyro_mag ** 2
            )
        )

        if len(
            dominant_freqs
        ) == 0:

            mean_freq = 0
            freq_std = 999

        else:

            mean_freq = np.mean(
                dominant_freqs
            )

            self.freq_history.append(
                mean_freq
            )

            if len(
                self.freq_history
            ) >= 3:

                freq_std = np.std(
                    self.freq_history
                )

            else:

                freq_std = 999

        if len(
            energy_ratios
        ) == 0:

            mean_energy_ratio = 0

        else:

            mean_energy_ratio = np.mean(
                energy_ratios
            )

        # Axis coherence: dominant frequencies of gx, gy, gz
        dom_freqs_axes = []
        for axis_data in [gx, gy, gz]:
            axis_data_centered = axis_data - np.mean(axis_data)
            fft_axis = np.abs(rfft(axis_data_centered))
            freq_axis = rfftfreq(len(axis_data_centered), d=1/self.sample_rate)
            mask = (freq_axis >= 3) & (freq_axis <= 9)
            if np.any(mask):
                band_fft_axis = fft_axis[mask]
                band_freq_axis = freq_axis[mask]
                dom_freq = band_freq_axis[np.argmax(band_fft_axis)]
                dom_freqs_axes.append(dom_freq)
            else:
                dom_freqs_axes.append(0)
        axis_coherence = np.std(dom_freqs_axes)
        coherence_std = axis_coherence

        # Axis dominance: energy distribution 3-9 Hz per axis
        energy_per_axis = []
        total_energy_axes = 0
        for axis_data in [gx, gy, gz]:
            axis_data_centered = axis_data - np.mean(axis_data)
            fft_axis = np.abs(rfft(axis_data_centered))
            freq_axis = rfftfreq(len(axis_data_centered), d=1/self.sample_rate)
            mask = (freq_axis >= 3) & (freq_axis <= 9)
            band_fft_axis = fft_axis[mask]
            energy = np.sum(band_fft_axis ** 2)
            energy_per_axis.append(energy)
            total_energy_axes += energy
        if total_energy_axes > 0:
            dominance = max(energy_per_axis) / total_energy_axes
        else:
            dominance = 0

        motion_gate = (
            rms_motion > 1.5 and
            rms_motion < 40
        )

        frequency_gate = (
            3.5 <= mean_freq <= 7.0
        )

        energy_gate = (
            mean_energy_ratio > 0.15
        )

        stability_gate = (
            freq_std < 1.50
        )

        coherence_gate = (
            coherence_std < 1.00
        )

        dominance_gate = (
            dominance > 0.55
        )

        rest_gate = (
            rest_index < 0.20
        )

        tremor_score = 0

        if motion_gate:
            tremor_score += 20

        if frequency_gate:
            tremor_score += 20

        if energy_gate:
            tremor_score += 20

        if stability_gate:
            tremor_score += 15

        if coherence_gate:
            tremor_score += 10

        if dominance_gate:
            tremor_score += 15

        if rms_motion < 1.0:
            tremor_score = 0

        if mean_energy_ratio < 0.20:
            tremor_score = max(
                0,
                tremor_score - 20
            )

        if not rest_gate:
            tremor_score = max(
                0,
                tremor_score - 20
            )

        if (
            not motion_gate or
            not frequency_gate or
            not stability_gate
        ):
            tremor_score = min(tremor_score, 40)

        if tremor_score >= 70:

            self.persistence = min(
                self.persistence + 1,
                5
            )

        else:

            self.persistence = max(
                self.persistence - 2,
                0
            )

        tremor_detected = (
            self.persistence >= 4 and
            motion_gate and
            frequency_gate and
            stability_gate
        )

        self.total_windows += 1

        if tremor_detected:
            self.tremor_windows += 1

        tremor_burden = (
            100.0 *
            self.tremor_windows /
            self.total_windows
        )

        confidence = min(
            100,
            int(tremor_score)
        )

        if tremor_score < 50:
            severity = "NONE"
        elif tremor_score < 75:
            severity = "MILD"
        elif tremor_score < 90:
            severity = "MODERATE"
        else:
            severity = "SEVERE"

        print(
            f"DEBUG | RMS={rms_motion:.2f} "
            f"Freq={mean_freq:.2f} "
            f"Band={mean_energy_ratio:.3f} "
            f"Score={tremor_score} "
            f"Persist={self.persistence}"
        )

        return {

            "rms_motion":
                rms_motion,

            "dominant_frequency":
                mean_freq,

            "frequency_std":
                freq_std,

            "band_ratio":
                mean_energy_ratio,

            "best_axis":
                max(
                    [("gx", energy_per_axis[0]), ("gy", energy_per_axis[1]), ("gz", energy_per_axis[2])],
                    key=lambda x: x[1]
                )[0],

            "motion_gate":
                motion_gate,

            "frequency_gate":
                frequency_gate,

            "energy_gate":
                energy_gate,

            "stability_gate":
                stability_gate,

            "coherence_gate":
                coherence_gate,

            "dominance_gate":
                dominance_gate,

            "rest_gate":
                rest_gate,

            "tremor_score":
                tremor_score,

            "tremor_detected":
                tremor_detected,

            "persistence":
                self.persistence,

            "confidence":
                confidence,

            "tremor_burden":
                tremor_burden,

            "rest_index":
                rest_index,

            "axis_coherence":
                axis_coherence,

            "axis_dominance":
                dominance,

            "severity":
                severity
        }
