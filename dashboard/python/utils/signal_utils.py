import numpy as np


def vector_magnitude(x, y, z):
    """
    Compute magnitude of 3-axis signal.
    """

    return np.sqrt(x**2 + y**2 + z**2)


def remove_dc(signal):
    """
    Remove DC component.
    """

    return signal - np.mean(signal)


def normalize(signal):
    """
    Zero mean, unit variance.
    """

    std = np.std(signal)

    if std < 1e-8:
        return signal * 0

    return (signal - np.mean(signal)) / std


def rms(signal):
    return np.sqrt(np.mean(signal**2))


def signal_energy(signal):
    return np.sum(signal**2)


def zero_crossings(signal):

    return np.sum(np.diff(np.sign(signal)) != 0)


def jerk(signal):

    return np.diff(signal)


def moving_average(signal, window=5):

    kernel = np.ones(window) / window

    return np.convolve(signal, kernel, mode="same")
