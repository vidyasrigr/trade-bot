"""
Paper-trade fill realism (P0 Stage 4.1).

Paper fills must be MORE pessimistic than the backtest's mid-pricing, or paper
results lie. This model:
  - buys fill WORSE than the ask, sells fill WORSE than the bid (slippage beyond
    the touch, not at mid),
  - rejects trades that wouldn't realistically fill: wide spread, thin OI, stale
    quote, insufficient depth,
  - is fully DETERMINISTIC (no random missing-fill) so paper results reproduce
    run-to-run,
  - handles multi-leg structures: if ANY leg fails its gate, the whole ticket is
    a no-fill (you can't leg into a defined-risk structure at will).

Thresholds default to the runbook spec; tune per-symbol later (PENDING R.2).
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class LegFill:
    filled: bool
    price: float | None
    reason: str            # filled | no_quote | wide_spread | low_oi | stale | thin_depth


@dataclass(frozen=True)
class TicketFill:
    filled: bool
    legs: tuple[LegFill, ...]
    net_price: float | None   # signed: debit > 0, credit < 0 (sum of qty*leg_price)
    reason: str


@dataclass(frozen=True)
class PaperFillModel:
    slip_frac: float = 0.05          # fraction of spread paid beyond the touch
    max_spread_frac: float = 0.08    # skip if (ask-bid) > this * mid
    min_open_interest: int = 100
    max_stale_seconds: int = 30

    def fill_leg(self, *, bid: float, ask: float, qty: int, opening: bool,
                 open_interest: int | None = None, stale_seconds: float = 0.0,
                 depth: int | None = None) -> LegFill:
        """
        qty: +N long, -N short. opening: True for entry, False for exit.
        Buying (long-open or short-close) pays ask + slip; selling receives bid - slip.
        """
        if not bid or not ask or ask <= 0:
            return LegFill(False, None, "no_quote")
        mid = (bid + ask) / 2.0
        spread = ask - bid
        if mid > 0 and spread > self.max_spread_frac * mid:
            return LegFill(False, None, "wide_spread")
        if open_interest is not None and open_interest < self.min_open_interest:
            return LegFill(False, None, "low_oi")
        if stale_seconds and stale_seconds > self.max_stale_seconds:
            return LegFill(False, None, "stale")
        if depth is not None and qty and depth < abs(qty):
            return LegFill(False, None, "thin_depth")
        buying = (qty > 0) == opening
        price = (ask + self.slip_frac * spread) if buying else (bid - self.slip_frac * spread)
        return LegFill(True, round(max(0.0, price), 4), "filled")

    def fill_ticket(self, legs: list[dict], *, opening: bool = True) -> TicketFill:
        """
        legs: [{bid, ask, qty, open_interest?, stale_seconds?, depth?}, ...].
        Returns a TicketFill; net_price is signed (sum qty*price). If any leg
        fails its gate, the whole ticket is rejected (no partial structures).
        """
        results = []
        for lg in legs:
            results.append(self.fill_leg(
                bid=float(lg.get("bid") or 0), ask=float(lg.get("ask") or 0),
                qty=int(lg.get("qty") or 0), opening=opening,
                open_interest=lg.get("open_interest"),
                stale_seconds=float(lg.get("stale_seconds") or 0),
                depth=lg.get("depth"),
            ))
        if not results or not all(r.filled for r in results):
            bad = next((r.reason for r in results if not r.filled), "no_quote")
            return TicketFill(False, tuple(results), None, bad)
        net = sum(int(lg.get("qty") or 0) * r.price for lg, r in zip(legs, results))
        return TicketFill(True, tuple(results), round(net, 4), "filled")
