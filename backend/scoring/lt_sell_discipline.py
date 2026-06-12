"""
LT Sell Discipline — 6 proactive exit triggers + 7-condition bubble score.

Runs after each quarterly earnings cycle for all portfolio holdings.
Fires alerts to Discord when any trigger is active.

Research basis:
  - Fundamental deterioration shows up 2-4 months before price breaks
  - 20% trailing stop alone is reactive; these triggers are proactive
  - Sources: Piotroski (2000), Sloan (1996 accruals), AQR factor research
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from loguru import logger

from core.config import settings


@dataclass
class SellTriggerResult:
    symbol: str
    triggers_fired: list[str] = field(default_factory=list)
    bubble_conditions_met: int = 0
    bubble_score_action: str | None = None   # 'trim_50pct', 'exit', None
    should_alert: bool = False
    summary: str = ""


# ---------------------------------------------------------------------------
# Trigger 1: Piotroski collapse
# ---------------------------------------------------------------------------

def check_piotroski_collapse(
    current_fscore: int | None,
    prior_fscore: int | None,
) -> str | None:
    """
    Fires when F-score drops from ≥7 to ≤4 in one quarter.
    Historical precedent: quality deterioration precedes price drop by 1-2 quarters.
    """
    if current_fscore is None or prior_fscore is None:
        return None
    if prior_fscore >= 7 and current_fscore <= 4:
        return "piotroski_collapse"
    return None


# ---------------------------------------------------------------------------
# Trigger 2: Estimate revision reversal
# ---------------------------------------------------------------------------

def check_estimate_revision_reversal(
    eps_revision_history: list[str],  # list of 'up'|'down'|'flat', most recent first
) -> str | None:
    """
    Fires when 2+ consecutive quarters of analyst EPS cuts following an upward run.
    """
    if len(eps_revision_history) < 3:
        return None

    # Pattern: was going up, now 2+ downs
    recent = eps_revision_history[:2]
    prior = eps_revision_history[2:5]

    if all(d == "down" for d in recent) and any(d == "up" for d in prior):
        return "estimate_revision_reversal"
    return None


# ---------------------------------------------------------------------------
# Trigger 3: Revenue deceleration breakpoint
# ---------------------------------------------------------------------------

def check_revenue_deceleration(
    rev_qoq_history: list[float],  # most recent first
    gm_history: list[float],
) -> str | None:
    """
    Fires when QoQ revenue acceleration turns negative for 2 consecutive quarters
    AND gross margin is simultaneously contracting.
    """
    if len(rev_qoq_history) < 3 or len(gm_history) < 3:
        return None

    # Rev acceleration = diff between consecutive QoQ growth rates
    accel_q0 = rev_qoq_history[0] - rev_qoq_history[1]
    accel_q1 = rev_qoq_history[1] - rev_qoq_history[2]

    rev_decel_2q = accel_q0 < 0 and accel_q1 < 0

    # Gross margin contracting
    gm_contracting = gm_history[0] < gm_history[1] and gm_history[1] < gm_history[2]

    if rev_decel_2q and gm_contracting:
        return "revenue_deceleration_breakpoint"
    return None


# ---------------------------------------------------------------------------
# Trigger 4: ROIC crosses below WACC
# ---------------------------------------------------------------------------

def check_roic_wacc_crossover(
    roic_current: float | None,
    roic_prior: float | None,
    wacc_proxy: float = 0.10,
) -> str | None:
    """
    Fires when ROIC was above WACC and has now crossed below.
    Indicates the company is destroying value — quality deterioration.
    """
    if roic_current is None or roic_prior is None:
        return None
    if roic_prior > wacc_proxy and roic_current <= wacc_proxy:
        return "roic_below_wacc"
    return None


# ---------------------------------------------------------------------------
# Trigger 5: Earnings momentum exhaustion
# ---------------------------------------------------------------------------

def check_earnings_momentum_exhaustion(
    eps_growth_history: list[float],  # YoY%, most recent first
) -> str | None:
    """
    Fires when EPS growth decelerates from >20% YoY to <5% in a single quarter.
    Flags for review — not a hard sell, but a thesis re-evaluation.
    """
    if len(eps_growth_history) < 2:
        return None
    if eps_growth_history[1] > 20 and eps_growth_history[0] < 5:
        return "earnings_momentum_exhaustion"
    return None


# ---------------------------------------------------------------------------
# Trigger 6: Insider selling cluster
# ---------------------------------------------------------------------------

def check_insider_selling_cluster(
    insider_transactions: list[dict],  # last 90 days: [{name, role, action, shares_pct}]
) -> str | None:
    """
    Fires when 3+ C-suite insiders sell >1% of their individual holdings within 90 days.
    """
    sells = [
        t for t in insider_transactions
        if t.get("action") == "sell"
        and t.get("shares_pct", 0) > 0.01  # >1% of their position
        and t.get("role", "").upper() in (
            "CEO", "CFO", "COO", "CTO", "CHAIRMAN", "DIRECTOR", "PRESIDENT", "SVP", "EVP"
        )
    ]
    if len(sells) >= 3:
        return "insider_selling_cluster"
    return None


# ---------------------------------------------------------------------------
# 7-Condition Bubble Score
# ---------------------------------------------------------------------------

def check_bubble_score(
    pe_current: float | None,
    pe_5yr_mean: float | None,
    ps_current: float | None,
    ps_5yr_mean: float | None,
    ev_ebitda_current: float | None,
    ev_ebitda_sector_median: float | None,
    price_12m_return: float | None,
    peg_current: float | None,
    short_interest_pct: float | None,
    analyst_consecutive_upgrades: int = 0,
    institutional_ownership_pct: float | None = None,
) -> tuple[int, list[str], str | None]:
    """
    Returns (conditions_met, which_conditions, action).
    action: 'trim_50pct' (≥4), 'exit' (≥6), None
    """
    met: list[str] = []

    if pe_current and pe_5yr_mean and pe_5yr_mean > 0:
        if pe_current > 2.5 * pe_5yr_mean:
            met.append("pe_gt_2_5x_mean")

    if ps_current and ps_5yr_mean and ps_5yr_mean > 0:
        if ps_current > 3.0 * ps_5yr_mean:
            met.append("ps_gt_3x_mean")

    if ev_ebitda_current and ev_ebitda_sector_median and ev_ebitda_sector_median > 0:
        if ev_ebitda_current > 2.0 * ev_ebitda_sector_median:
            met.append("ev_ebitda_gt_2x_sector")

    if price_12m_return is not None and peg_current is not None:
        if price_12m_return > 1.0 and peg_current > 2.0:  # up >100% AND PEG >2.0
            met.append("parabolic_with_high_peg")

    if short_interest_pct is not None and short_interest_pct < 0.02:
        met.append("shorts_capitulated")

    if analyst_consecutive_upgrades >= 3:
        met.append("analyst_euphoria")

    if institutional_ownership_pct is not None and institutional_ownership_pct > 0.90:
        met.append("no_incremental_buyers")

    count = len(met)
    if count >= 6:
        action = "exit"
    elif count >= 4:
        action = "trim_50pct"
    else:
        action = None

    return count, met, action


# ---------------------------------------------------------------------------
# Main runner
# ---------------------------------------------------------------------------

async def run_sell_discipline(
    symbol: str,
    fundamentals: dict[str, Any],
    price_data: dict[str, Any],
    insider_data: list[dict],
) -> SellTriggerResult:
    """
    Run all 6 triggers + bubble score for a symbol.
    `fundamentals` should contain keys from FMP quarterly data.
    `price_data` should contain {price_12m_return, short_interest_pct, etc.}.
    """
    result = SellTriggerResult(symbol=symbol)

    # Trigger 1: Piotroski collapse
    t1 = check_piotroski_collapse(
        fundamentals.get("piotroski_current"),
        fundamentals.get("piotroski_prior"),
    )
    if t1:
        result.triggers_fired.append(t1)

    # Trigger 2: Estimate revision reversal
    t2 = check_estimate_revision_reversal(
        fundamentals.get("eps_revision_history", [])
    )
    if t2:
        result.triggers_fired.append(t2)

    # Trigger 3: Revenue deceleration breakpoint
    t3 = check_revenue_deceleration(
        fundamentals.get("rev_qoq_history", []),
        fundamentals.get("gm_history", []),
    )
    if t3:
        result.triggers_fired.append(t3)

    # Trigger 4: ROIC/WACC crossover
    t4 = check_roic_wacc_crossover(
        fundamentals.get("roic_current"),
        fundamentals.get("roic_prior"),
    )
    if t4:
        result.triggers_fired.append(t4)

    # Trigger 5: Earnings momentum exhaustion
    t5 = check_earnings_momentum_exhaustion(
        fundamentals.get("eps_growth_history", [])
    )
    if t5:
        result.triggers_fired.append(t5)

    # Trigger 6: Insider selling cluster
    t6 = check_insider_selling_cluster(insider_data)
    if t6:
        result.triggers_fired.append(t6)

    # Bubble score
    count, conditions, action = check_bubble_score(
        pe_current=fundamentals.get("pe_current"),
        pe_5yr_mean=fundamentals.get("pe_5yr_mean"),
        ps_current=fundamentals.get("ps_current"),
        ps_5yr_mean=fundamentals.get("ps_5yr_mean"),
        ev_ebitda_current=fundamentals.get("ev_ebitda"),
        ev_ebitda_sector_median=fundamentals.get("ev_ebitda_sector_median"),
        price_12m_return=price_data.get("price_12m_return"),
        peg_current=fundamentals.get("peg"),
        short_interest_pct=price_data.get("short_interest_pct"),
        analyst_consecutive_upgrades=fundamentals.get("analyst_consecutive_upgrades", 0),
        institutional_ownership_pct=fundamentals.get("institutional_ownership_pct"),
    )

    result.bubble_conditions_met = count
    if action:
        result.bubble_score_action = action
        result.triggers_fired.append(f"bubble_score_{count}_of_7")

    result.should_alert = bool(result.triggers_fired)

    # Build summary
    if result.triggers_fired:
        descs = {
            "piotroski_collapse": "Piotroski F-score collapsed (≥7 → ≤4)",
            "estimate_revision_reversal": "2+ consecutive analyst EPS cuts after upward run",
            "revenue_deceleration_breakpoint": "Revenue decel for 2 qtrs + gross margin compressing",
            "roic_below_wacc": "ROIC crossed below WACC — value destruction",
            "earnings_momentum_exhaustion": "EPS growth decelerated from >20% to <5% in one quarter",
            "insider_selling_cluster": "3+ C-suite insiders sold >1% of holdings in 90 days",
        }
        fired_text = "; ".join(descs.get(t, t) for t in result.triggers_fired if not t.startswith("bubble"))
        if result.bubble_score_action:
            fired_text += f"; Bubble score {count}/7 → {result.bubble_score_action.replace('_', ' ')}"
        result.summary = f"⚠ SELL TRIGGERS [{symbol}]: {fired_text}"
        logger.warning(result.summary)
    else:
        result.summary = f"✓ No sell triggers fired for {symbol}"

    # Discord alert
    if result.should_alert and settings.DISCORD_WEBHOOK_URL:
        await _send_sell_alert(result)

    return result


async def _send_sell_alert(result: SellTriggerResult) -> None:
    """Send sell trigger alert to Discord."""
    import httpx

    action_map = {
        "piotroski_collapse": "🔴 REVIEW IMMEDIATELY",
        "revenue_deceleration_breakpoint": "🟠 EXIT WITHIN 20 DAYS",
        "roic_below_wacc": "🔴 EXIT — value destruction",
        "bubble_score_action": "🟡 TRIM or EXIT",
    }

    color = 0xff4444 if any(
        t in result.triggers_fired for t in ("piotroski_collapse", "roic_below_wacc")
    ) else 0xff8800

    fields = [
        {"name": "Triggers Fired", "value": "\n".join(f"• {t}" for t in result.triggers_fired), "inline": False},
    ]
    if result.bubble_score_action:
        fields.append({"name": "Bubble Score Action", "value": result.bubble_score_action.replace("_", " ").title(), "inline": True})

    payload = {
        "embeds": [{
            "title": f"⚠ LT Sell Trigger: {result.symbol}",
            "description": result.summary,
            "color": color,
            "fields": fields,
        }]
    }

    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            await client.post(settings.DISCORD_WEBHOOK_URL, json=payload)
    except Exception as e:
        logger.debug(f"Discord sell alert failed: {e}")
