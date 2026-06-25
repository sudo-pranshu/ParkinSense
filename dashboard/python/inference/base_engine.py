"""
ParkinSense V2

Base Inference Engine

Every future detector
(rule based, ML, deep learning)
inherits from this class.
"""


class InferenceEngine:

    def predict(self, feature_vector):

        raise NotImplementedError(
            "InferenceEngine.predict() not implemented."
        )
