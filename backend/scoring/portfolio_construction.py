"""
Portfolio Construction: pairwise correlation block + volatility-adjusted position sizing.

Research basis:
  - AQR: NVDA+AMD+INTC+KLAC have 0.85+ pairwise correlation despite looking like different sectors
  - Rolling 60-day return correlations replace static sector-membership proxies
  - Volatility-adjusted sizing: target 0.5% portfolio risk contribution per position
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd
from loguru import logger

from core.config import settings


@dataclass
class PositionSizing:
    symbol: str
    base_size_pct: float       # raw vol-adjusted size (% of portfolio)
    adjusted_size_pct: float   # after correlation haircut
    max_pct: float = 0.04      # hard cap
    warning: str | None = None


@dataclass
class CorrelationCheck:
    symbol: str
    max_pairwise_corr: float = 0.0
    correlated_with: str | None = None
    avg_portfolio_corr: float = 0.0
    blocks_full_position: bool = False
    size_haircut_pct: float = 0.0
    warning: str | None = None


# ---------------------------------------------------------------------------
# Rolling pairwise correlation matrix
# ---------------------------------------------------------------------------

def compute_pairwise_correlations(
    returns: pd.DataFrame,  # columns = symbols, index = dates, values = daily returns
    window: int = 60,
) -> pd.DataFrame:
    """
    Compute rolling 60-day pairwise return correlations.
    Returns a (symbols × symbols) DataFrame with the latest window's correlations.
    """
    if returns.empty or len(returns) < window:
        return pd.DataFrame()

    recent = returns.tail(window).dropna(axis=1, how="all")
    if recent.empty:
        return pd.DataFrame()

    return recent.corr()


def check_correlation_block(
    new_symbol: str,
    new_symbol_returns: pd.Series,
    existing_holdings: dict[str, pd.Series],  # symbol → daily returns
    window: int = 60,
    block_threshold: float = 0.55,   # average portfolio correlation above this = flag
    haircut_threshold: float = 0.75, # pairwise with any single holding above this = 40% haircut
) -> CorrelationCheck:
    """
    Check if adding `new_symbol` to the portfolio raises correlation too high.

    Rules (from plan):
    - If adding new position raises avg portfolio pairwise corr above 0.55 → flag
    - If new stock has pairwise corr > 0.75 with any existing holding → cut size 40%
    """
    check = CorrelationCheck(symbol=new_symbol)

    if not existing_holdings:
        return check

    # Build combined returns DataFrame
    all_returns = {new_symbol: new_symbol_returns}
    all_returns.update(existing_holdings)
    df = pd.DataFrame(all_returns).tail(window).dropna()

    if len(df) < 20:
        check.warning = "Insufficient return history for correlation check"
        return check

    corr_matrix = df.corr()

    if new_symbol not in corr_matrix.columns:
        return check

    new_symbol_corrs = corr_matrix[new_symbol].drop(new_symbol)

    # Max pairwise correlation with any existing holding
    check.max_pairwise_corr = float(new_symbol_corrs.max())
    most_correlated = new_symbol_corrs.idxmax()
    check.correlated_with = str(most_correlated)

    # Average correlation of new symbol with all existing holdings
    check.avg_portfolio_corr = float(new_symbol_corrs.mean())

    # Apply rules
    if check.max_pairwise_corr > haircut_threshold:
        check.blocks_full_position = True
        check.size_haircut_pct = 40.0
        check.warning = (
            f"{new_symbol} has {check.max_pairwise_corr:.2f} pairwise correlation with "
            f"{check.correlated_with} — applying 40% size reduction"
        )
        logger.warning(check.warning)

    elif check.avg_portfolio_corr > block_threshold:
        check.blocks_full_position = True
        check.size_haircut_pct = 25.0
        check.warning = (
            f"Adding {new_symbol} raises avg portfolio correlation to "
            f"{check.avg_portfolio_corr:.2f} (>{block_threshold}) — applying 25% size reduction"
        )
        logger.warning(check.warning)

    return check


# ---------------------------------------------------------------------------
# Volatility-adjusted position sizing
# ---------------------------------------------------------------------------

def compute_vol_adjusted_size(
    symbol: str,
    returns: pd.Series,
    portfolio_value: float,
    target_risk_contribution_pct: float = 0.005,  # 0.5% of portfolio annualized vol
    kelly_fraction: float = 0.50,
    max_size_pct: float = 0.04,
    correlation_haircut: float = 0.0,  # from CorrelationCheck.size_haircut_pct / 100
) -> PositionSizing:
    """
    Position size such that this position contributes `target_risk_contribution_pct`
    of portfolio value in annualized vol terms.

    position_size = target_risk_pct / annual_vol_of_stock

    Then apply:
    - correlation haircut
    - Kelly fraction
    - hard cap at max_size_pct
    """
    sizing = PositionSizing(symbol=symbol, base_size_pct=0.0, adjusted_size_pct=0.0)

    if returns.empty or len(returns) < 20:
        sizing.base_size_pct = settings.BASE_POSITION_SIZE_PCT
        sizing.adjusted_size_pct = settings.BASE_POSITION_SIZE_PCT
        sizing.warning = "Insufficient return history — using base position size"
        return sizing

    # Annualized vol
    daily_vol = float(returns.tail(252).std())
    annual_vol = daily_vol * np.sqrt(252)

    if annual_vol <= 0:
        sizing.base_size_pct = settings.BASE_POSITION_SIZE_PCT
        sizing.adjusted_size_pct = settings.BASE_POSITION_SIZE_PCT
        return sizing

    # Raw size from risk targeting
    base_size = target_risk_contribution_pct / annual_vol

    # Apply Kelly fraction
    base_size = base_size * kelly_fraction

    # Cap at max
    base_size = min(base_size, max_size_pct)

    sizing.base_size_pct = round(base_size, 4)

    # Apply correlation haircut
    adjusted = base_size * (1 - correlation_haircut)
    adjusted = min(adjusted, max_size_pct)
    sizing.adjusted_size_pct = round(adjusted, 4)

    # Dollar amount
    dollar_size = adjusted * portfolio_value
    logger.debug(
        f"Sizing {symbol}: annual_vol={annual_vol:.1%}, base={base_size:.1%}, "
        f"adjusted={adjusted:.1%} (${dollar_size:,.0f})"
    )

    return sizing


# ---------------------------------------------------------------------------
# Full portfolio check (run before any new LT position)
# ---------------------------------------------------------------------------

async def evaluate_new_position(
    symbol: str,
    sector: str,
    all_holdings: list[dict],  # list of {symbol, shares, avg_cost_basis}
    ohlcv_loader=None,  # async fn(symbol) → pd.DataFrame
) -> dict:
    """
    Full portfolio construction check for a new LT position entry.
    Returns a dict with sizing recommendation and all checks.
    """
    if ohlcv_loader is None:
        return {
            "symbol": symbol,
            "warning": "No OHLCV loader provided — cannot run correlation/vol check",
            "recommended_size_pct": settings.BASE_POSITION_SIZE_PCT,
        }

    # Load returns for new symbol
    try:
        df_new = await ohlcv_loader(symbol)
        if df_new.empty or "close" not in df_new.columns:
            return {"symbol": symbol, "warning": "No price data", "recommended_size_pct": 0.02}
        returns_new = df_new["close"].pct_change().dropna()
    except Exception as e:
        logger.debug(f"Portfolio eval: failed to load {symbol}: {e}")
        return {"symbol": symbol, "warning": str(e), "recommended_size_pct": 0.02}

    # Load returns for existing holdings
    existing_returns: dict[str, pd.Series] = {}
    for h in all_holdings:
        sym = h.get("symbol", "")
        if not sym or sym == symbol:
            continue
        try:
            df_h = await ohlcv_loader(sym)
            if not df_h.empty and "close" in df_h.columns:
                existing_returns[sym] = df_h["close"].pct_change().dropna()
        except Exception:
            pass

    # Correlation check
    corr_check = check_correlation_block(symbol, returns_new, existing_returns)

    # Vol-adjusted sizing
    sizing = compute_vol_adjusted_size(
        symbol,
        returns_new,
        portfolio_value=settings.PAPER_PORTFOLIO_VALUE,
        correlation_haircut=corr_check.size_haircut_pct / 100.0,
    )

    return {
        "symbol": symbol,
        "recommended_size_pct": sizing.adjusted_size_pct,
        "base_size_pct": sizing.base_size_pct,
        "correlation_check": {
            "max_pairwise_corr": corr_check.max_pairwise_corr,
            "correlated_with": corr_check.correlated_with,
            "avg_portfolio_corr": corr_check.avg_portfolio_corr,
            "haircut_pct": corr_check.size_haircut_pct,
            "warning": corr_check.warning,
        },
        "sizing_warning": sizing.warning,
    }
