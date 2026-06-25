"""
ParkinSense V2

Rule Based Inference Engine
"""

from dashboard.python.inference.base_engine import InferenceEngine

from dashboard.python.detector.multiaxis_detector import MultiAxisDetector
from dashboard.python.detector.confidence import ConfidenceEstimator
from dashboard.python.detector.state_machine import TremorStateMachine


class RuleInferenceEngine(InferenceEngine):

    def __init__(self):

        self.detector = MultiAxisDetector()

        self.confidence = ConfidenceEstimator()

        self.state_machine = TremorStateMachine()

    def predict(
        self,
        features,
        context
    ):

        detector = self.detector.detect(
            features,
            context
        )

        confidence = self.confidence.estimate(

            detector["frequency_std"],

            detector["band_ratio"],

            detector["axis_agreement"],

            context

        )

        detector["confidence"] = confidence

        detector["state"] = self.state_machine.update(

            detector["score"]

        )

        return detector
