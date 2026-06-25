import numpy as np

from dashboard.python.pipelines.motion_pipeline import MotionPipeline

fs = 104

t = np.arange(0,4,1/fs)

gx = np.sin(2*np.pi*5*t)

gy = np.sin(2*np.pi*5*t)

gz = np.sin(2*np.pi*5*t)

ax = np.zeros_like(t)

ay = np.zeros_like(t)

az = np.ones_like(t)

pipeline = MotionPipeline(fs)

result = pipeline.process(

    ax,

    ay,

    az,

    gx,

    gy,

    gz

)

print(result["feature_vector"])

print()

print(result["result"])

print()

print(result["context"])

