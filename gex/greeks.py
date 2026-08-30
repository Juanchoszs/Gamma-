"""Vectorized Black-Scholes calculations."""
from __future__ import annotations

import numpy as np
from scipy.stats import norm

_EPS = 1e-12


def _d1_d2(s, k, t, r, sigma):
    s = np.asarray(s, dtype=float)
    k = np.asarray(k, dtype=float)
    t = np.maximum(np.asarray(t, dtype=float), _EPS)
    sigma = np.maximum(np.asarray(sigma, dtype=float), _EPS)
    d1 = (np.log(s / k) + (r + 0.5 * sigma**2) * t) / (sigma * np.sqrt(t))
    d2 = d1 - sigma * np.sqrt(t)
    return d1, d2


def call_price(s, k, t, r, sigma):
    d1, d2 = _d1_d2(s, k, t, r, sigma)
    return s * norm.cdf(d1) - k * np.exp(-r * t) * norm.cdf(d2)


def put_price(s, k, t, r, sigma):
    d1, d2 = _d1_d2(s, k, t, r, sigma)
    return k * np.exp(-r * t) * norm.cdf(-d2) - s * norm.cdf(-d1)


def call_delta(s, k, t, r, sigma):
    d1, _ = _d1_d2(s, k, t, r, sigma)
    return norm.cdf(d1)


def put_delta(s, k, t, r, sigma):
    return call_delta(s, k, t, r, sigma) - 1.0


def gamma(s, k, t, r, sigma):
    """Gamma, identical for calls and puts."""
    d1, _ = _d1_d2(s, k, t, r, sigma)
    t = np.maximum(np.asarray(t, dtype=float), _EPS)
    sigma = np.maximum(np.asarray(sigma, dtype=float), _EPS)
    return norm.pdf(d1) / (np.asarray(s, dtype=float) * sigma * np.sqrt(t))


def vega(s, k, t, r, sigma):
    """Vega for one volatility point, without division by 100."""
    d1, _ = _d1_d2(s, k, t, r, sigma)
    t = np.maximum(np.asarray(t, dtype=float), _EPS)
    return np.asarray(s, dtype=float) * norm.pdf(d1) * np.sqrt(t)


def call_theta(s, k, t, r, sigma):
    """Annualized theta; divide by 365 for daily theta."""
    d1, d2 = _d1_d2(s, k, t, r, sigma)
    t = np.maximum(np.asarray(t, dtype=float), _EPS)
    return (
        -np.asarray(s, dtype=float) * norm.pdf(d1) * sigma / (2 * np.sqrt(t))
        - r * np.asarray(k, dtype=float) * np.exp(-r * t) * norm.cdf(d2)
    )


def vanna(s, k, t, r, sigma):
    """Vanna, identical for calls and puts.

    Multiply by 0.01 to measure the effect of a one-point volatility move.
    """
    d1, d2 = _d1_d2(s, k, t, r, sigma)
    sigma = np.maximum(np.asarray(sigma, dtype=float), _EPS)
    return -norm.pdf(d1) * d2 / sigma


def charm(s, k, t, r, sigma):
    """Delta decay from the passage of time, using trader convention."""
    d1, d2 = _d1_d2(s, k, t, r, sigma)
    t = np.maximum(np.asarray(t, dtype=float), _EPS)
    sigma = np.maximum(np.asarray(sigma, dtype=float), _EPS)
    return -norm.pdf(d1) * (2 * r * t - d2 * sigma * np.sqrt(t)) / (2 * t * sigma * np.sqrt(t))


def charm_per_day(s, k, t, r, sigma):
    """Delta change over one elapsed day."""
    return charm(s, k, t, r, sigma) / 365.0


def implied_vol(price, s, k, t, r, is_call, tol=1e-6, max_iter=60):
    """Solve implied volatility with vectorized Newton-Raphson iterations."""
    price = np.asarray(price, dtype=float)
    s = np.broadcast_to(np.asarray(s, dtype=float), price.shape).copy()
    k = np.broadcast_to(np.asarray(k, dtype=float), price.shape).copy()
    t = np.broadcast_to(np.asarray(t, dtype=float), price.shape).copy()
    is_call = np.broadcast_to(np.asarray(is_call, dtype=bool), price.shape)

    intrinsic = np.where(is_call, np.maximum(s - k * np.exp(-r * t), 0.0),
                         np.maximum(k * np.exp(-r * t) - s, 0.0))
    valid = (price > intrinsic + 1e-10) & (t > 0)

    sigma = np.full(price.shape, 0.5)
    for _ in range(max_iter):
        model = np.where(is_call, call_price(s, k, t, r, sigma), put_price(s, k, t, r, sigma))
        v = vega(s, k, t, r, sigma)
        step = np.where(v > 1e-12, (model - price) / np.maximum(v, 1e-12), 0.0)
        sigma = np.clip(sigma - np.clip(step, -0.5, 0.5), 1e-4, 10.0)
    model = np.where(is_call, call_price(s, k, t, r, sigma), put_price(s, k, t, r, sigma))
    converged = np.abs(model - price) < np.maximum(tol, 1e-4 * price)
    return np.where(valid & converged, sigma, np.nan)


def put_theta(s, k, t, r, sigma):
    d1, d2 = _d1_d2(s, k, t, r, sigma)
    t = np.maximum(np.asarray(t, dtype=float), _EPS)
    return (
        -np.asarray(s, dtype=float) * norm.pdf(d1) * sigma / (2 * np.sqrt(t))
        + r * np.asarray(k, dtype=float) * np.exp(-r * t) * norm.cdf(-d2)
    )
