from dashboard.python.detector.confidence import ConfidenceEstimator

ce = ConfidenceEstimator()

print(

    ce.estimate(

        frequency_std=0.15,

        band_ratio=0.30,

        axis_agreement=0.92,

        context={"state":"REST"}

    )

)

print(

    ce.estimate(

        frequency_std=2.2,

        band_ratio=0.05,

        axis_agreement=0.45,

        context={"state":"ACTIVE"}

    )

)
