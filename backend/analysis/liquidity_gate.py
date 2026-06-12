"""Options Liquidity Gate — gates stocks out if options spread is too wide."""

from loguru import logger
from data.tradier import get_tradier


async def check_options_liquidity(symbol: str) -> dict:
    """
    Returns {ok: bool, note: str, spread_pct: float, avg_oi: int, alternative: str}
    Rejects if bid-ask > 10% of mid OR OI < 500.
    """
    tradier = get_tradier()
    try:
        chain = await tradier.get_best_chain(symbol, min_dte=14, max_dte=45)
        if not chain:
            return {"ok": False, "note": "No options chain found"}

        import numpy as np
        last_close = None
        try:
            quote = await tradier.get_quote(symbol)
            last_close = float(quote.get("last") or quote.get("close") or 0)
        except Exception:
            pass

        atm = sorted(chain, key=lambda c: abs(float(c.get("strike", 0)) - (last_close or float(c.get("strike", 0)))))[:4]

        spreads, ois = [], []
        for c in atm:
            bid = float(c.get("bid") or 0)
            ask = float(c.get("ask") or 0)
            oi  = int(c.get("open_interest") or 0)
            if bid > 0 and ask > 0:
                spreads.append((ask - bid) / ((ask + bid) / 2))
                ois.append(oi)

        if not spreads:
            return {"ok": False, "note": "Cannot compute spread from chain"}

        avg_spread = float(np.mean(spreads))
        avg_oi = float(np.mean(ois)) if ois else 0

        issues = []
        if avg_spread > 0.10:
            issues.append(f"bid-ask spread {round(avg_spread*100,1)}% > 10%")
        if avg_oi < 500:
            issues.append(f"avg OI {round(avg_oi)} < 500")

        if issues:
            # Suggest ETF alternative
            alt = _suggest_alternative(symbol)
            return {
                "ok": False,
                "note": f"Poor liquidity: {'; '.join(issues)}",
                "spread_pct": round(avg_spread * 100, 1),
                "avg_oi": round(avg_oi),
                "alternative": alt,
            }

        return {
            "ok": True,
            "note": f"Liquidity OK: spread={round(avg_spread*100,1)}%, OI={round(avg_oi)}",
            "spread_pct": round(avg_spread * 100, 1),
            "avg_oi": round(avg_oi),
        }
    except Exception as e:
        logger.debug(f"Liquidity check failed for {symbol}: {e}")
        return {"ok": True, "note": "Could not verify — proceeding"}  # fail-open for Stage 2


def _suggest_alternative(symbol: str) -> str:
    """Map illiquid stock to a more liquid sector ETF."""
    sector_etf_map = {
        "RDW": "ROKT", "RKLB": "ROKT", "ASTS": "ROKT", "VORB": "ROKT",
        "ONDS": "ITA",  "KTOS": "ITA",
        "OKLO": "NLR",  "SMR": "NLR", "LEU": "NLR",
        "IONQ": "QTUM", "RGTI": "QTUM", "QUBT": "QTUM",
        "LITE": "SMH",  "COHR": "SMH",
        "NBIS": "WCLD",
    }
    return sector_etf_map.get(symbol, "consider shares or sector ETF")
