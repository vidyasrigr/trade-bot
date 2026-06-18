"""
Black-Scholes implied-vol inversion from option mid prices.

Why this exists:
  MarketData Starter returns NO greeks and NO IV on historical chains (every
  cached parquet has mid_iv==0, delta==0). That blocks the skew_25d /
  iv_call_put_spread / iv_term_slope family, which all need per-strike IV+delta.
  But the cached chains DO carry bid, ask, strike, and underlying_price — enough
  to invert Black-Scholes and recover IV, then compute delta analytically.

Assumptions: continuous rate r (default 4%), dividend yield q (default 0). For
European-style index/large-cap options near 45 DTE this is accurate enough to
rank a cross-sectional skew signal; it is NOT a replacement for a real vol
surface (PENDING: ORATS/LiveVol). American early-exercise error is small for the
~16-25 delta OTM strikes the skew signal uses.
"""

from __future__ import annotations

import math

import numpy as np
import pandas as pd
from scipy.optimize import brentq
from scipy.stats import norm


def bs_price(S: float, K: float, T: float, r: float, sigma: float,
             is_call: bool, q: float = 0.0) -> float:
    if T <= 0 or sigma <= 0 or S <= 0 or K <= 0:
        intrinsic = max(0.0, (S - K) if is_call else (K - S))
        return intrinsic
    d1 = (math.log(S / K) + (r - q + 0.5 * sigma * sigma) * T) / (sigma * math.sqrt(T))
    d2 = d1 - sigma * math.sqrt(T)
    if is_call:
        return S * math.exp(-q * T) * norm.cdf(d1) - K * math.exp(-r * T) * norm.cdf(d2)
    return K * math.exp(-r * T) * norm.cdf(-d2) - S * math.exp(-q * T) * norm.cdf(-d1)


def bs_delta(S: float, K: float, T: float, r: float, sigma: float,
             is_call: bool, q: float = 0.0) -> float:
    if T <= 0 or sigma <= 0 or S <= 0 or K <= 0:
        return 0.0
    d1 = (math.log(S / K) + (r - q + 0.5 * sigma * sigma) * T) / (sigma * math.sqrt(T))
    return math.exp(-q * T) * (norm.cdf(d1) if is_call else norm.cdf(d1) - 1.0)


def implied_vol(price: float, S: float, K: float, T: float, r: float,
                is_call: bool, q: float = 0.0) -> float | None:
    """Brent-solve for sigma. Returns None when the price is outside no-arb bounds."""
    if price is None or price <= 0 or S <= 0 or K <= 0 or T <= 0:
        return None
    intrinsic = max(0.0, (S - K) if is_call else (K - S)) * math.exp(-q * T)
    upper = (S * math.exp(-q * T)) if is_call else (K * math.exp(-r * T))
    if price <= intrinsic + 1e-6 or price >= upper:
        return None
    f = lambda sig: bs_price(S, K, T, r, sig, is_call, q) - price
    try:
        return float(brentq(f, 1e-4, 5.0, maxiter=100, xtol=1e-6))
    except (ValueError, RuntimeError):
        return None


def enrich_chain_iv(df: pd.DataFrame, as_of: object, expiry: object,
                    r: float = 0.04, q: float = 0.0) -> pd.DataFrame:
    """
    Add iv + delta columns to a cached chain DataFrame (cols: strike, option_type,
    bid, ask, underlying_price). T is computed from as_of -> expiry. Rows where
    inversion fails (price outside bounds, deep ITM, stale quote) get NaN.
    """
    if df.empty:
        return df.assign(iv=np.nan, delta=np.nan)
    T = (pd.Timestamp(expiry) - pd.Timestamp(as_of)).days / 365.0
    ivs, deltas = [], []
    for row in df.itertuples(index=False):
        try:
            S = float(row.underlying_price)
            K = float(row.strike)
            mid = (float(row.bid) + float(row.ask)) / 2.0
            is_call = str(row.option_type).upper().startswith("C")
        except (AttributeError, TypeError, ValueError):
            ivs.append(np.nan); deltas.append(np.nan); continue
        iv = implied_vol(mid, S, K, T, r, is_call, q)
        ivs.append(iv if iv is not None else np.nan)
        deltas.append(bs_delta(S, K, T, r, iv, is_call, q) if iv else np.nan)
    return df.assign(iv=ivs, delta=deltas)
