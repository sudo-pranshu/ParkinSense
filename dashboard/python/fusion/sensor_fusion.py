import numpy as np


class SensorFusion:

    def __init__(self):

        self.gravity = np.zeros(3)

        self.alpha = 0.98

    def update(self, ax, ay, az, gx, gy, gz):

        accel = np.array([ax, ay, az])

        gyro = np.array([gx, gy, gz])

        accel_mag = np.linalg.norm(accel)

        gyro_mag = np.linalg.norm(gyro)

        if accel_mag > 1e-6:

            accel_unit = accel / accel_mag

        else:

            accel_unit = np.zeros(3)

        self.gravity = (

            self.alpha * self.gravity +

            (1 - self.alpha) * accel_unit

        )

        linear_accel = accel - self.gravity

        linear_mag = np.linalg.norm(linear_accel)

        motion_mag = np.sqrt(

            linear_mag ** 2 +

            gyro_mag ** 2

        )

        return {

            "gravity": self.gravity.copy(),

            "linear_acceleration": linear_accel,

            "acceleration_magnitude": accel_mag,

            "gyro_magnitude": gyro_mag,

            "linear_magnitude": linear_mag,

            "motion_magnitude": motion_mag

        }
