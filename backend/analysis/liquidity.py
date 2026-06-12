"""Category 14: Liquidity & Execution (5%)"""

import numpy as np
import pandas as pd
from analysis.engine import CategoryScore


async def analyze(symbol: str, df: pd.DataFrame, chain: list[dict]) -> CategoryScore:
    signals = []
    score = 5.0
    direction = "neutral"

    # Stock liquidity (volume)
    if not df.empty and "volume" in df.columns:
        avg_vol = float(df["volume"].tail(20).mean())
        today_vol = float(df["volume"].iloc[-1]) if len(df) > 0 else 0
        last_close = float(df["close"].iloc[-1]) if len(df) > 0 else 0
        dollar_vol = avg_vol * last_close
        signals.append({"name": "avg_daily_dollar_volume", "value": round(dollar_vol / 1e6, 1), "unit": "M"})
        if dollar_vol > 50_000_000:
            score += 1
            signals.append({"name": "high_stock_liquidity", "direction": "favorable"})
        elif dollar_vol < 1_000_000:
            score -= 2
            signals.append({"name": "low_stock_liquidity", "note": "Execution risk"})

    # Options liquidity: ATM bid-ask spread
    if chain:
        last_close = float(df["close"].iloc[-1]) if not df.empty else 0
        atm = sorted(chain, key=lambda c: abs(float(c.get("strike", 0)) - last_close))[:4]
        spreads = []
        ois = []
        for c in atm:
            bid = float(c.get("bid") or 0)
            ask = float(c.get("ask") or 0)
            oi  = int(c.get("open_interest") or 0)
            if bid > 0 and ask > 0:
                spread_pct = (ask - bid) / ((ask + bid) / 2)
                spreads.append(spread_pct)
                ois.append(oi)

        if spreads:
            avg_spread = np.mean(spreads)
            avg_oi = np.mean(ois)
            signals.append({"name": "atm_bid_ask_spread_pct", "value": round(avg_spread * 100, 1)})
            signals.append({"name": "avg_atm_oi", "value": round(avg_oi)})

            # Professional threshold: <1.5% spread = excellent; >10% = reject
            spread_pct_display = round(avg_spread * 100, 2)
            if avg_spread < 0.015:
                score += 2.5
                signals.append({"name": "tight_options_spread", "value": spread_pct_display,
                                "direction": "favorable", "note": "<1.5% — institutional quality liquidity"})
            elif avg_spread < 0.05:
                score += 1.0
                signals.append({"name": "good_options_spread", "value": spread_pct_display,
                                "note": "1.5-5% — acceptable for retail"})
            elif avg_spread < 0.10:
                score -= 0.5
                signals.append({"name": "moderate_options_spread", "value": spread_pct_display,
                                "note": "5-10% — elevated slippage risk"})
            else:
                score -= 2.5
                signals.append({"name": "wide_options_spread", "value": spread_pct_display,
                                "direction": "bearish", "note": ">10% spread — consider ETF alternative"})

            if avg_oi > 500:
                score += 0.5
                signals.append({"name": "adequate_oi", "value": round(avg_oi)})
            elif avg_oi < 100:
                score -= 1
                signals.append({"name": "low_oi", "note": "Hard to exit"})

    score = max(0.0, min(10.0, score))
    weight = 5.0
    return CategoryScore("liquidity", weight, score, weight * score / 10, direction, signals,
                        f"Options spread={'N/A' if not chain else round(np.mean(spreads)*100,1) if spreads else 'N/A'}%")
