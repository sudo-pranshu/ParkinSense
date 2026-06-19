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
        gx,
        gy,
        gz
    ):

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

        gx = np.array(
            self.gx_buffer
        )

        gy = np.array(
            self.gy_buffer
        )

        gz = np.array(
            self.gz_buffer
        )

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

        axis_scores = []

        for signal in [
            ("gx", gx),
            ("gy", gy),
            ("gz", gz)
        ]:

            axis_name = signal[0]

            axis_data = (
                signal[1] -
                np.mean(signal[1])
            )

            fft_axis = np.abs(
                rfft(axis_data)
            )

            freq_axis = rfftfreq(
                len(axis_data),
                d=1/self.sample_rate
            )

            axis_mask = (
                (freq_axis >= 3) &
                (freq_axis <= 9)
            )

            score = np.sum(
                fft_axis[
                    axis_mask
                ] ** 2
            )

            axis_scores.append(
                (
                    axis_name,
                    score
                )
            )

        best_axis, _ = max(
            axis_scores,
            key=lambda x: x[1]
        )

        motion_gate = (
            rms_motion > 10 and
            rms_motion < 70
        )

        frequency_gate = (
            4.0 <= mean_freq <= 7.0
        )

        energy_gate = (
            mean_energy_ratio > 0.30
        )

        stability_gate = (
            freq_std < 1.50
        )

        tremor_score = 0

        if motion_gate:
            tremor_score += 25

        if frequency_gate:
            tremor_score += 25

        if energy_gate:
            tremor_score += 25

        if stability_gate:
            tremor_score += 25

        if rms_motion < 5:
            tremor_score = 0

        if mean_energy_ratio < 0.20:
            tremor_score = max(
                0,
                tremor_score - 25
            )

        if tremor_score >= 75:

            self.persistence = min(
                self.persistence + 1,
                5
            )

        else:

            self.persistence = max(
                self.persistence - 1,
                0
            )

        tremor_detected = (
            self.persistence >= 3
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
            int(
                mean_energy_ratio * 50 +
                (25 if frequency_gate else 0) +
                (25 if stability_gate else 0)
            )
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
                best_axis,

            "motion_gate":
                motion_gate,

            "frequency_gate":
                frequency_gate,

            "energy_gate":
                energy_gate,

            "stability_gate":
                stability_gate,

            "tremor_score":
                tremor_score,

            "tremor_detected":
                tremor_detected,

            "persistence":
                self.persistence,

            "confidence":
                confidence,

            "tremor_burden":
                tremor_burden
        }
