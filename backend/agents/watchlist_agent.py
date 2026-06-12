"""
Watchlist Agent — one agent instance per watched ticker.

Design principles:
  - Isolated Redis namespace per ticker: watchlist:{symbol}:state
  - Isolated pgvector memory: only lessons about THIS ticker (no cross-ticker bleed)
  - Runs every 30 min during market hours via APScheduler
  - Detects score delta ≥ 10 points between refreshes → Discord alert
  - Per-ticker IC weights override global weights after 20+ closed trades
  - Auto-updates its scoring approach based on win/loss history for this ticker
"""

from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from typing import Optional

import orjson
from loguru import logger

from core.config import settings


@dataclass
class TickerState:
    symbol: str
    added_at: str
    last_refreshed: str = ""
    current_score: float = 0.0
    prev_score: float = 0.0
    current_direction: str = "neutral"
    current_price: float = 0.0
    iv_rank: float = 50.0
    regime: str = "unknown"
    total_trades: int = 0
    wins: int = 0
    losses: int = 0
    win_rate: float = 0.0
    avg_r_multiple: float = 0.0
    score_history: list = field(default_factory=list)   # [{ts, score, direction}]
    active_alerts: list = field(default_factory=list)
    ticker_lessons: list = field(default_factory=list)   # top-5 lessons for this ticker
    factor_overrides: dict = field(default_factory=dict)  # per-ticker IC weight overrides
    notes: str = ""  # freeform notes V can add via UI


class WatchlistAgent:
    """Dedicated agent for one watched ticker."""

    def __init__(self, symbol: str):
        self.symbol = symbol.upper()
        self._state_key = f"watchlist:{self.symbol}:state"

    # ── Public API ────────────────────────────────────────────────────────────

    async def refresh(self) -> TickerState:
        """
        Refresh the ticker state. Called every 30 min.
        Returns updated state; sends Discord alert if score delta ≥ 10.
        """
        prev_state = await self._load_state()

        # Quick score (Stage 2-equivalent, no Claude)
        score, direction, price, iv_rank = await self._quick_score()

        now = datetime.now(timezone.utc).isoformat()
        prev_score = prev_state.current_score if prev_state else 0.0

        # Build updated history (keep last 48 points ≈ 24h at 30-min intervals)
        history = (prev_state.score_history if prev_state else [])[-47:]
        history.append({"ts": now, "score": round(score, 1), "direction": direction})

        state = TickerState(
            symbol=self.symbol,
            added_at=prev_state.added_at if prev_state else now,
            last_refreshed=now,
            current_score=round(score, 1),
            prev_score=round(prev_score, 1),
            current_direction=direction,
            current_price=round(price, 2),
            iv_rank=round(iv_rank, 1),
            regime=await self._get_regime(),
            total_trades=prev_state.total_trades if prev_state else 0,
            wins=prev_state.wins if prev_state else 0,
            losses=prev_state.losses if prev_state else 0,
            win_rate=prev_state.win_rate if prev_state else 0.0,
            avg_r_multiple=prev_state.avg_r_multiple if prev_state else 0.0,
            score_history=history,
            active_alerts=[],
            ticker_lessons=await self._get_ticker_lessons(),
            factor_overrides=prev_state.factor_overrides if prev_state else {},
            notes=prev_state.notes if prev_state else "",
        )

        # Signal change detection
        delta = score - prev_score
        if abs(delta) >= 10.0 and prev_score > 0:
            direction_changed = state.current_direction != (prev_state.current_direction if prev_state else direction)
            alert = self._build_signal_alert(state, delta, direction_changed)
            state.active_alerts.append(alert)
            await self._send_discord_alert(state, alert)

        # High conviction setup detection
        if score >= 75 and direction in ("bullish", "bearish"):
            state.active_alerts.append({
                "type": "high_conviction",
                "message": f"{self.symbol}: Score {score:.0f}/100 — high-conviction {direction} setup ready for analysis",
                "severity": "info",
            })
            if prev_score < 75:  # Only notify on the transition
                from api.discord_notify import send_alert
                await send_alert(
                    title=f"🎯 High Conviction Setup — ${self.symbol}",
                    message=f"Score jumped to **{score:.0f}/100** ({direction}). Ready for full Stage 4 analysis.",
                    alert_type="new_setup",
                    symbol=self.symbol,
                    fields=[
                        {"name": "IV Rank", "value": f"{iv_rank:.0f}th pct", "inline": True},
                        {"name": "Price", "value": f"${price:.2f}", "inline": True},
                        {"name": "Regime", "value": state.regime, "inline": True},
                    ],
                )

        # Momentum crossover detection — fires specific "buy now" alerts
        momentum_events = await self._check_momentum_events()
        if momentum_events:
            await self._send_momentum_alert(state, momentum_events)
            for ev in momentum_events:
                state.active_alerts.append({
                    "type": "momentum_event",
                    "event": ev["event"],
                    "message": ev["label"],
                    "severity": "warning" if ev.get("strength") == "strong" else "info",
                })

        await self._save_state(state)
        logger.debug(f"Watchlist refresh {self.symbol}: score={score:.1f} (delta={delta:+.1f})")
        return state

    async def learn_from_closed_trade(self, trade: dict) -> None:
        """
        Called by postmortem.py when a trade for this ticker closes.
        Updates per-ticker win/loss stats and adjusts factor overrides.
        """
        state = await self._load_state()
        if not state:
            return

        pnl = float(trade.get("realized_pnl") or 0)
        r_multiple = float(trade.get("r_multiple") or 0)

        state.total_trades += 1
        if pnl > 0:
            state.wins += 1
        else:
            state.losses += 1
        state.win_rate = round(state.wins / state.total_trades * 100, 1) if state.total_trades > 0 else 0.0

        # Rolling average R-multiple
        alpha = 0.2
        state.avg_r_multiple = round(
            (1 - alpha) * state.avg_r_multiple + alpha * r_multiple, 3
        )

        # Update factor overrides based on what worked/failed for THIS ticker
        factor_scores = trade.get("factor_scores") or {}
        outcome = 1 if pnl > 0 else -1
        for factor, score in factor_scores.items():
            factor_direction = 1 if float(score) > 5 else -1
            ic_contrib = factor_direction * outcome
            prev = state.factor_overrides.get(factor, {"ic": 0.05, "count": 0})
            count = prev["count"] + 1
            new_ic = (1 - 0.15) * prev["ic"] + 0.15 * ic_contrib
            state.factor_overrides[factor] = {"ic": round(new_ic, 4), "count": count}

        await self._save_state(state)

    async def get_state(self) -> Optional[TickerState]:
        return await self._load_state()

    async def add_note(self, note: str) -> None:
        state = await self._load_state()
        if state:
            state.notes = note
            await self._save_state(state)

    # ── Private helpers ───────────────────────────────────────────────────────

    async def _quick_score(self) -> tuple[float, str, float, float]:
        """Run a fast Stage-1/2 score without Claude. Returns (score, direction, price, iv_rank)."""
        try:
            import yfinance as yf
            import numpy as np
            ticker = yf.Ticker(self.symbol)
            hist = ticker.history(period="3mo")
            if hist.empty:
                return 50.0, "neutral", 0.0, 50.0

            close = hist["Close"]
            price = float(close.iloc[-1])

            # Trend: EMA alignment
            ema8  = float(close.ewm(span=8).mean().iloc[-1])
            ema21 = float(close.ewm(span=21).mean().iloc[-1])
            ema50 = float(close.ewm(span=50).mean().iloc[-1])
            trend_score = (
                (2.0 if price > ema8  else -2.0) +
                (2.0 if ema8  > ema21 else -1.0) +
                (2.0 if ema21 > ema50 else -1.0)
            )  # -5 to +6

            # Momentum: RSI
            delta = close.diff()
            gain = delta.clip(lower=0).ewm(com=13).mean()
            loss = (-delta.clip(upper=0)).ewm(com=13).mean()
            rsi = float(100 - 100 / (1 + gain.iloc[-1] / (loss.iloc[-1] + 1e-9)))

            # Volume anomaly
            vol_20_avg = float(hist["Volume"].tail(20).mean())
            vol_today  = float(hist["Volume"].iloc[-1])
            vol_ratio  = vol_today / vol_20_avg if vol_20_avg > 0 else 1.0

            # IV rank (approximate from 30-day HV)
            log_returns = np.log(close / close.shift(1)).dropna()
            hv30 = float(np.std(log_returns.tail(30)) * np.sqrt(252) * 100)
            hv_series = np.array([np.std(log_returns.iloc[max(0,i-30):i]) * np.sqrt(252) * 100
                                   for i in range(30, len(log_returns)+1)])
            iv_rank = float(np.mean(hv_series < hv30) * 100) if len(hv_series) > 20 else 50.0

            # Composite score
            raw = (
                50.0
                + trend_score * 5
                + (rsi - 50) * 0.3
                + (vol_ratio - 1) * 5
            )
            score = float(np.clip(raw, 0, 100))
            direction = "bullish" if trend_score > 2 and rsi > 50 else \
                        "bearish" if trend_score < -2 and rsi < 50 else "neutral"

            return score, direction, price, iv_rank

        except Exception as e:
            logger.debug(f"Quick score failed for {self.symbol}: {e}")
            return 50.0, "neutral", 0.0, 50.0

    async def _get_regime(self) -> str:
        try:
            import yfinance as yf
            spy = yf.Ticker("SPY").history(period="3mo")
            if spy.empty:
                return "unknown"
            close = spy["Close"]
            ema50 = close.ewm(span=50).mean().iloc[-1]
            price = close.iloc[-1]
            vix = yf.Ticker("^VIX").history(period="5d")
            vix_level = float(vix["Close"].iloc[-1]) if not vix.empty else 20.0

            if vix_level > 30:
                return "high_vol"
            elif price > ema50:
                return "bull_trend"
            elif price < ema50:
                return "bear_trend"
            return "chop"
        except Exception:
            return "unknown"

    async def _get_ticker_lessons(self) -> list[dict]:
        """Fetch top-5 ticker-specific lessons from memory (pgvector)."""
        try:
            from core.database import AsyncSessionLocal
            from sqlalchemy import text
            async with AsyncSessionLocal() as session:
                result = await session.execute(text("""
                    SELECT lesson, r_multiple, regime, factors_that_worked, created_at
                    FROM memory_entries
                    WHERE symbol = :sym
                    ORDER BY ABS(r_multiple) DESC, created_at DESC
                    LIMIT 5
                """), {"sym": self.symbol})
                rows = result.fetchall()
            return [
                {"lesson": r[0], "r_multiple": float(r[1] or 0),
                 "regime": r[2], "factors": r[3], "date": str(r[4])[:10]}
                for r in rows
            ]
        except Exception:
            return []

    async def _check_momentum_events(self) -> list[dict]:
        """
        Run full momentum analysis and return any fresh crossover events.
        Only fires on NEW crossovers (not previously seen — tracked via Redis TTL key).
        """
        try:
            import yfinance as yf
            import pandas as pd
            ticker = yf.Ticker(self.symbol)
            hist = ticker.history(period="3mo")
            if hist.empty or len(hist) < 22:
                return []

            df = hist.rename(columns=str.lower)[["open", "high", "low", "close", "volume"]]
            from analysis.momentum import analyze as analyze_momentum
            result = await analyze_momentum(self.symbol, df)

            # Extract momentum_events signal
            events_signal = next(
                (s for s in result.signals if s.get("name") == "momentum_events"), None
            )
            if not events_signal:
                return []

            all_events = events_signal.get("events", [])
            if not all_events:
                return []

            # De-duplicate: only fire if we haven't seen this event in the last 4 hours
            from core.redis_client import get_redis
            redis = get_redis()
            fresh = []
            for ev in all_events:
                dedup_key = f"watchlist:{self.symbol}:event:{ev['event']}"
                already_fired = await redis.get(dedup_key)
                if not already_fired:
                    fresh.append(ev)
                    await redis.setex(dedup_key, 4 * 3600, "1")  # 4-hour cooldown

            return fresh

        except Exception as e:
            logger.debug(f"Momentum event check failed for {self.symbol}: {e}")
            return []

    async def _send_momentum_alert(self, state: TickerState, events: list[dict]) -> None:
        """Send a Discord alert with specific option recommendation for momentum events."""
        from api.discord_notify import send_alert

        # Build the specific option suggestion based on current price and direction
        price = state.current_price or 0.0
        iv_rank = state.iv_rank or 50.0
        direction = state.current_direction

        # Simple strike/expiry suggestion (DTE 14-21, delta ~0.40 ATM)
        if direction == "bullish":
            # ATM call, next 2-3 week Friday
            strike_hint = round(price * 1.02 / 0.5) * 0.5  # ~2% OTM
            structure = "Bull call spread or outright call"
            emoji = "🟢"
        elif direction == "bearish":
            strike_hint = round(price * 0.98 / 0.5) * 0.5
            structure = "Bear put spread or outright put"
            emoji = "🔴"
        else:
            strike_hint = round(price / 0.5) * 0.5
            structure = "Wait for clear direction"
            emoji = "⚪"

        event_labels = [f"• {ev['label']}" for ev in events]
        strong_events = [e for e in events if e.get("strength") == "strong"]
        severity = "warning" if strong_events else "info"

        # Combine all event labels into the message
        events_text = "\n".join(event_labels)
        suggestion = (
            f"**Suggested:** {structure}\n"
            f"Strike area: ~${strike_hint:.2f} | DTE: 14-21 days\n"
            f"IV Rank: {iv_rank:.0f}th pct | Score: {state.current_score:.0f}/100"
        )

        await send_alert(
            title=f"{emoji} Momentum Signal — ${self.symbol}",
            message=f"**Crossover events detected:**\n{events_text}\n\n{suggestion}",
            alert_type=severity,
            symbol=self.symbol,
            fields=[
                {"name": "Current Price", "value": f"${price:.2f}", "inline": True},
                {"name": "Direction", "value": direction.title(), "inline": True},
                {"name": "Events", "value": str(len(events)), "inline": True},
            ],
        )

    def _build_signal_alert(self, state: TickerState, delta: float, direction_changed: bool) -> dict:
        direction = "up" if delta > 0 else "down"
        return {
            "type": "score_change",
            "delta": round(delta, 1),
            "severity": "warning" if abs(delta) >= 20 else "info",
            "message": (
                f"{self.symbol}: Score moved {delta:+.0f} points → {state.current_score:.0f}/100"
                + (f" | Direction flipped to {state.current_direction}" if direction_changed else "")
            ),
        }

    async def _send_discord_alert(self, state: TickerState, alert: dict) -> None:
        from api.discord_notify import send_alert
        severity = alert.get("severity", "info")
        await send_alert(
            title=f"📈 Score Change — ${self.symbol}",
            message=alert["message"],
            alert_type=severity,
            symbol=self.symbol,
            fields=[
                {"name": "Score", "value": f"{state.prev_score:.0f} → {state.current_score:.0f}", "inline": True},
                {"name": "Direction", "value": state.current_direction.title(), "inline": True},
                {"name": "IV Rank", "value": f"{state.iv_rank:.0f}th pct", "inline": True},
            ],
        )

    async def _load_state(self) -> Optional[TickerState]:
        from core.redis_client import get_redis
        try:
            redis = get_redis()
            raw = await redis.get(self._state_key)
            if raw:
                data = orjson.loads(raw)
                return TickerState(**data)
        except Exception as e:
            logger.debug(f"Could not load watchlist state for {self.symbol}: {e}")
        return None

    async def _save_state(self, state: TickerState) -> None:
        from core.redis_client import get_redis
        try:
            redis = get_redis()
            await redis.set(self._state_key, orjson.dumps(asdict(state)))
        except Exception as e:
            logger.debug(f"Could not save watchlist state for {self.symbol}: {e}")


# ── Watchlist registry ────────────────────────────────────────────────────────

_WATCHLIST_KEY = "watchlist:symbols"


async def get_watchlist_symbols() -> list[str]:
    from core.redis_client import get_redis
    try:
        redis = get_redis()
        raw = await redis.get(_WATCHLIST_KEY)
        return orjson.loads(raw) if raw else []
    except Exception:
        return []


async def add_to_watchlist(symbol: str) -> WatchlistAgent:
    from core.redis_client import get_redis
    symbol = symbol.upper()
    redis = get_redis()
    symbols = await get_watchlist_symbols()
    if symbol not in symbols:
        symbols.append(symbol)
        await redis.set(_WATCHLIST_KEY, orjson.dumps(symbols))

    agent = WatchlistAgent(symbol)
    existing = await agent.get_state()
    if not existing:
        # Initialize with first refresh
        await agent.refresh()
    return agent


async def remove_from_watchlist(symbol: str) -> None:
    from core.redis_client import get_redis
    symbol = symbol.upper()
    redis = get_redis()
    symbols = await get_watchlist_symbols()
    if symbol in symbols:
        symbols.remove(symbol)
        await redis.set(_WATCHLIST_KEY, orjson.dumps(symbols))
        await redis.delete(f"watchlist:{symbol}:state")


async def refresh_all_watchlist() -> list[dict]:
    """Refresh all watched tickers. Called by APScheduler every 30 min."""
    symbols = await get_watchlist_symbols()
    if not symbols:
        return []

    results = []
    import asyncio
    agents = [WatchlistAgent(s) for s in symbols]
    states = await asyncio.gather(*[a.refresh() for a in agents], return_exceptions=True)

    for sym, state in zip(symbols, states):
        if isinstance(state, Exception):
            logger.warning(f"Watchlist refresh failed for {sym}: {state}")
        else:
            results.append(asdict(state))

    logger.info(f"Watchlist refresh complete: {len(results)}/{len(symbols)} symbols updated")
    return results
