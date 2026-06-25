"""
ParkinSense V2
Motion Processing Pipeline
"""

import numpy as np

from dashboard.python.filters.gravity import GravityRemoval
from dashboard.python.filters.notch import NotchFilter
from dashboard.python.filters.bandpass import ButterworthBandpass

from dashboard.python.features.feature_extractor import FeatureExtractor
from dashboard.python.features.feature_vector import FeatureVector

from dashboard.python.context.motion_context import MotionContext

from dashboard.python.inference.rule_engine import RuleInferenceEngine


class MotionPipeline:

    def __init__(self, fs=104):

        self.fs = fs

        self.gravity = GravityRemoval(fs)

        self.notch = NotchFilter(fs)

        self.bandpass = ButterworthBandpass(fs)

        self.extractor = FeatureExtractor(fs)

        self.context = MotionContext()

        self.engine = RuleInferenceEngine()

    def preprocess(self, signal):

        signal = self.notch.filter(signal)

        signal = self.bandpass.filter(signal)

        return signal

    def process(

        self,

        ax,

        ay,

        az,

        gx,

        gy,

        gz

    ):

        ax = self.gravity.remove(np.asarray(ax))

        ay = self.gravity.remove(np.asarray(ay))

        az = self.gravity.remove(np.asarray(az))

        context = self.context.classify(

            ax,

            ay,

            az

        )

        gx = self.preprocess(np.asarray(gx))

        gy = self.preprocess(np.asarray(gy))

        gz = self.preprocess(np.asarray(gz))

        gx_features = self.extractor.extract(gx)

        gy_features = self.extractor.extract(gy)

        gz_features = self.extractor.extract(gz)

        features = {

            "gx": gx_features,

            "gy": gy_features,

            "gz": gz_features

        }

        result = self.engine.predict(

            features,

            context

        )

        best = features[result["best_axis"]]

        fv = FeatureVector(

            rms=best["rms"],

            dominant_frequency=best["dominant_frequency"],

            band_ratio=best["band_ratio"],

            spectral_entropy=best["spectral_entropy"],

            spectral_centroid=best["spectral_centroid"],

            frequency_std=result["frequency_std"],

            axis_agreement=result["axis_agreement"],

            axis_dominance=result["axis_dominance"],

            best_axis=result["best_axis"],

            motion_state=context["state"],

            rest_index=result["rest_index"],

            features=features

        )

        result["frequency"]      = float(result["frequency"])
        result["frequency_std"]  = float(result["frequency_std"])
        result["band_ratio"]     = float(result["band_ratio"])
        result["axis_agreement"] = float(result["axis_agreement"])
        result["axis_dominance"] = float(result["axis_dominance"])
        result["rest_index"]     = float(result["rest_index"])
        result["score"]          = int(result["score"])
        result["confidence"]     = float(result["confidence"])

        return {

            "feature_vector": fv,

            "result": result,

            "context": context

        }
