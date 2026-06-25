from dashboard.python.detector.temporal import TemporalSmoother

ts = TemporalSmoother()

for score in [82, 79, 85, 83, 20, 84]:

    result = ts.update({
        "score": score,
        "frequency": 5.2,
        "confidence": 90
    })

    print(result)
