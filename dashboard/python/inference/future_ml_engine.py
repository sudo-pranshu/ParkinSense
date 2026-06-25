"""
ParkinSense V2

Future Machine Learning Engine

Placeholder.

Later this class will load:

Random Forest

XGBoost

LightGBM

or

CNN

without changing the rest
of ParkinSense.
"""

from dashboard.python.inference.base_engine import InferenceEngine


class FutureMLEngine(InferenceEngine):

    def __init__(self):

        pass

    def predict(
        self,
        feature_vector
    ):

        raise NotImplementedError(
            "ML engine not implemented yet."
        )
