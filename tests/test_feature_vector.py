from dashboard.python.features.feature_vector import FeatureVector

fv = FeatureVector(

    rms=0.8,

    dominant_frequency=5.1,

    band_ratio=0.32,

    spectral_entropy=0.42,

    spectral_centroid=5.4,

    frequency_std=0.15,

    axis_agreement=0.91,

    axis_dominance=0.84,

    best_axis="gx",

    motion_state="REST",

    rest_index=0.93,

    features={}
)

print(fv)
