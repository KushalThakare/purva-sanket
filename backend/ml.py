"""Demonstration models trained on generated normal windows, not factory data."""
from functools import lru_cache
import numpy as np
from sklearn.ensemble import IsolationForest

FEATURES = ["temperature_mean_c", "temperature_slope_c_per_s",
            "vibration_mean_ms2", "vibration_max_ms2"]


def features(rows):
    values = np.asarray(rows, dtype=float)  # seconds, degrees C, RMS m/s^2
    x = values[:, 0] - values[0, 0]
    slope = float(np.polyfit(x, values[:, 1], 1)[0]) if np.ptp(x) > 0 else 0.0
    return [float(values[:, 1].mean()), slope,
            float(values[:, 2].mean()), float(values[:, 2].max())]


@lru_cache(maxsize=1)
def models():
    rng = np.random.default_rng(42)
    result = {}
    for mode, temperature, vibration in [("PRODUCTION", 35, .10),
                                         ("CLEANING", 30, .06),
                                         ("MAINTENANCE", 28, .04)]:
        examples = []
        for _ in range(1200):
            t = np.arange(10, dtype=float)
            base = temperature + rng.uniform(-3, 3)
            slope = rng.uniform(-.10, .10)
            temp = base + slope * t + rng.normal(0, .25, 10)
            vib = np.maximum(0, vibration + rng.uniform(-.04, .04)
                             + rng.normal(0, .014, 10))
            examples.append(features(np.column_stack([t, temp, vib])))
        result[mode] = IsolationForest(n_estimators=80, contamination=.05,
                                      random_state=42).fit(examples)
    return result


def score(rows, mode):
    model = models()[mode]
    vector = [features(rows)]
    value = float(model.decision_function(vector)[0])
    return {"status": "ANOMALY" if value < 0 else "NORMAL",
            "decision_score": round(value, 4), "features": FEATURES,
            "values": [round(v, 4) for v in vector[0]],
            "training_source": "synthetic normal windows"}
