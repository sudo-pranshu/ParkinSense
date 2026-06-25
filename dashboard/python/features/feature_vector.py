"""
ParkinSense V2

Feature Vector

Unified feature representation used by
all inference engines.
"""

from dataclasses import dataclass
from typing import Dict


@dataclass
class FeatureVector:

    rms: float

    dominant_frequency: float

    band_ratio: float

    spectral_entropy: float

    spectral_centroid: float

    frequency_std: float

    axis_agreement: float

    axis_dominance: float

    best_axis: str

    motion_state: str

    rest_index: float

    features: Dict
