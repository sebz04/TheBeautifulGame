"""Distribution helpers so generated attributes look like real life.

Ratings are bell-shaped in (0, 1): `rating(z) = sigmoid(RATING_SCALE * z)` where `z` is a
standardized combination of latent factors. Money is log-normal (right-skewed).
"""

import math

import numpy as np

RATING_SCALE = 0.7


def rating(z: float) -> float:
    return round(1.0 / (1.0 + math.exp(-RATING_SCALE * z)), 4)


def combine(
    rng: np.random.Generator, mu: float, terms: list[tuple[float, float]], noise: float
) -> float:
    """Standardized mix of latent factors (each ~N(0, 1)) plus noise, shifted by `mu`.

    The weighted sum is rescaled to unit variance so ratings keep a realistic spread no
    matter how many factors feed them.
    """
    total = sum(w * f for w, f in terms) + noise * float(rng.standard_normal())
    sd = math.sqrt(sum(w * w for w, _ in terms) + noise * noise)
    return mu + total / sd


def truncated_normal(
    rng: np.random.Generator, mean: float, sd: float, lo: float, hi: float
) -> float:
    while True:
        x = float(rng.normal(mean, sd))
        if lo <= x <= hi:
            return x


def log_normal_money(
    rng: np.random.Generator, median_m: float, log_shift: float, log_sd: float
) -> float:
    """USD millions: median `median_m` at shift 0, right-skewed, rounded to $0.1m."""
    return round(median_m * math.exp(log_shift + log_sd * float(rng.standard_normal())), 1)


def stream(seed: int, name: str) -> np.random.Generator:
    """Independent, reproducible random stream per generator part."""
    return np.random.default_rng([seed, sum(ord(c) * (i + 1) for i, c in enumerate(name))])
