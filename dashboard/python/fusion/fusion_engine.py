"""
ParkinSense
Fusion Engine

Converts MotionPipeline output into one standardized object that
every downstream module (dashboard, logger, analytics) can consume.
"""

import time


class FusionEngine:

    def process(self, pipeline_output):

        result = pipeline_output["result"]
        context = pipeline_output["context"]
        ppg = pipeline_output["ppg"]
        fv = pipeline_output["feature_vector"]

        return {

            # ---------- metadata ----------

            "timestamp": time.time(),

            # ---------- motion ----------

            "motion": {

                "state": context["state"],

                "confidence": result["confidence"],

                "rest_index": result["rest_index"]

            },

            # ---------- tremor ----------

            "tremor": {

                "detected": result["tremor"],

                "score": result["score"],

                "severity": result["severity"],

                "frequency": result["frequency"],

                "best_axis": result["best_axis"],

                "band_ratio": result["band_ratio"],

                "confidence": result["confidence"]

            },

            # ---------- physiology ----------

            "physiology": {

                "heart_rate": ppg["heart_rate"],

                "spo2": ppg["spo2"],

                "signal_quality": ppg["signal_quality"],

                "sensor_status": ppg["sensor_status"],

                "finger_detected": ppg["finger_detected"],

                "hrv": ppg["hrv"]

            },

            # ---------- diagnostics ----------

            "feature_vector": fv,

            "raw": pipeline_output

        }
