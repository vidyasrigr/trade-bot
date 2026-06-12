"""
LangGraph agent pipeline:
Scanner → [4 parallel analysts] → Trader → Adversary → [Rebuttal loop if challenged] → RiskManager → OptionsSelection

Architecture:
  - All Claude calls go through agents.hooks (pre/post/error hooks)
  - Trader + RiskManager use structured output (Anthropic tool_use) via output_models
  - Adversary uses Pydantic validation with 3× retry (see adversary.py)
  - Eval-optimizer loop: if adversary risk_override > 15, trader must rebut challenges
  - Conditional early exit: total_score < 40 skips all LLM calls (not worth analyzing)
  - 4 analyst agents run in parallel with asyncio.gather
"""

import asyncio
from typing import Any, TypedDict

from loguru import logger

from agents import hooks
from agents.output_models import RiskAssessment, TraderRebuttal, TraderThesis
from core.config import settings
from analysis.engine import run_analysis, AnalysisResult


# ── Conviction threshold below which we skip all LLM analysis ──────────────
_MIN_SCORE_FOR_ANALYSIS = 40


class AgentState(TypedDict):
    symbol: str
    stage3_data: dict
    cross_context: str
    analysis_result: dict
    fundamental_report: str
    technical_report: str
    volatility_report: str
    sentiment_report: str
    trader_thesis: str
    adversary_report: str        # devil's advocate challenge (Ollama deepseek-r1)
    risk_assessment: str
    trade_structure: dict
    order_ticket: dict
    conviction_score: float
    total_score: float
    direction: str
    vol_regime: str


# ── JSON schemas for Anthropic tool_use structured output ───────────────────

_TRADER_SCHEMA = TraderThesis.model_json_schema()
_REBUTTAL_SCHEMA = TraderRebuttal.model_json_schema()
_RISK_SCHEMA = RiskAssessment.model_json_schema()


async def run_analysis_graph(stage3_item: dict, cross_context: str) -> dict:
    """
    Full LangGraph analysis for one symbol.
    Returns dict with trade_thesis, order_ticket, conviction_score.
    """
    symbol = stage3_item["symbol"]
    logger.info(f"Running LangGraph analysis for {symbol}")

    # Step 1: Run quantitative analysis engine
    analysis = await run_analysis(symbol)

    # Conditional edge: skip LLM analysis if score is too low
    if analysis.total_score < _MIN_SCORE_FOR_ANALYSIS:
        logger.info(f"[{symbol}] Score {analysis.total_score:.0f} < {_MIN_SCORE_FOR_ANALYSIS} — skipping LLM agents")
        return _skip_result(symbol, analysis, stage3_item, reason="Score below minimum threshold")

    # Step 2: Retrieve memory, DNA, LT context in parallel
    memory_context, dna_context, lt_context = await asyncio.gather(
        _retrieve_memory(symbol, analysis),
        _get_dna_context(symbol),
        _get_lt_context(symbol),
        return_exceptions=True,
    )
    memory_context = "" if isinstance(memory_context, Exception) else memory_context
    dna_context = "" if isinstance(dna_context, Exception) else dna_context
    lt_context = "" if isinstance(lt_context, Exception) else lt_context

    state: AgentState = {
        "symbol": symbol,
        "stage3_data": stage3_item,
        "cross_context": cross_context,
        "analysis_result": analysis.to_dict(),
        "fundamental_report": "",
        "technical_report": "",
        "volatility_report": "",
        "sentiment_report": "",
        "trader_thesis": "",
        "adversary_report": "",
        "risk_assessment": "",
        "trade_structure": {},
        "order_ticket": {},
        "conviction_score": 0.0,
        "total_score": analysis.total_score,
        "direction": analysis.direction,
        "vol_regime": analysis.vol_regime,
    }

    # Step 3: Run 4 analysts in parallel
    reports = await asyncio.gather(
        fundamental_analyst(state, str(memory_context)),
        technical_analyst(state, str(memory_context)),
        volatility_analyst(state, str(memory_context)),
        sentiment_analyst_ollama(state),
        return_exceptions=True,
    )

    state["fundamental_report"] = reports[0] if not isinstance(reports[0], Exception) else "Unavailable"
    state["technical_report"]   = reports[1] if not isinstance(reports[1], Exception) else "Unavailable"
    state["volatility_report"]  = reports[2] if not isinstance(reports[2], Exception) else "Unavailable"
    state["sentiment_report"]   = reports[3] if not isinstance(reports[3], Exception) else "Unavailable"

    # Step 4: Trader synthesis (Opus) — structured output via tool_use
    combined_context = "\n\n".join(filter(None, [str(memory_context), str(dna_context), str(lt_context)]))
    await _run_trader(state, combined_context)

    # Step 4.5: Adversary challenge (deepseek-r1 via Ollama)
    adv_result = await _run_adversary(state, dna_context)
    state["adversary_report"] = adv_result.get("raw_response", "")
    discount = adv_result.get("risk_override", 0)
    if discount > 0:
        state["conviction_score"] = max(0.0, state["conviction_score"] - discount)
        logger.info(
            f"[{symbol}] Adversary challenged: -{discount} conviction. "
            f"Challenges: {adv_result.get('challenges', [])}"
        )

    # Step 4.6: Eval-optimizer loop — trader rebuttal when adversary challenges hard
    if discount > 15 and adv_result.get("challenges"):
        await _run_trader_rebuttal(state, adv_result["challenges"])

    # Step 5: Risk manager (Sonnet) — structured output
    await _run_risk_manager(state)

    # Step 6: Options selection (deterministic + chain query)
    state["trade_structure"] = await options_selection_agent(state, analysis)

    # Step 7: Build order ticket
    state["order_ticket"] = _build_order_ticket(state, analysis)

    return {
        "symbol": symbol,
        "total_score": analysis.total_score,
        "conviction_score": state["conviction_score"],
        "direction": analysis.direction,
        "vol_regime": analysis.vol_regime,
        "iv_percentile": analysis.iv_percentile,
        "trade_thesis": state["trader_thesis"],
        "risk_assessment": state["risk_assessment"],
        "category_scores": analysis.to_dict().get("category_scores", {}),
        "catalyst_flags": stage3_item.get("catalyst_flags", {}),
        "order_ticket": state["order_ticket"],
        "trade_structure": state["trade_structure"],
        "raw_signals": analysis.raw_signals,
    }


# ── Analyst agents ──────────────────────────────────────────────────────────

async def fundamental_analyst(state: AgentState, memory: str) -> str:
    cat_scores = state["analysis_result"].get("category_scores", {})
    fundamental = cat_scores.get("fundamental", {})
    macro = cat_scores.get("macro", {})

    # Context engineering: structured format instead of raw JSON dump
    fund_ctx = _format_fundamental_context(fundamental)
    macro_ctx = _format_category(macro)

    prompt = f"""You are the Fundamental Analyst for an options trading system. Be concise and specific.

Symbol: {state['symbol']}
Cross-stock context: {state['cross_context'][:500]}

FUNDAMENTAL SIGNALS:
{fund_ctx}

MACRO SIGNALS:
{macro_ctx}

RELEVANT MEMORY:
{memory[:400]}

In 3-4 sentences: What is the fundamental setup? Any catalyst? Any risk?
Focus on: earnings trajectory, analyst consensus gap, sector tailwinds/headwinds.
Flag immediately if Piotroski < 4 or gross margin is compressing."""

    return await hooks.llm_call("fundamental_analyst", state["symbol"], prompt, max_tokens=300)


async def technical_analyst(state: AgentState, memory: str) -> str:
    cat_scores = state["analysis_result"].get("category_scores", {})

    prompt = f"""You are the Technical Analyst for an options trading system. Be precise.

Symbol: {state['symbol']}

Trend: {_format_category(cat_scores.get('trend', {}))}
Support/Resistance: {_format_category(cat_scores.get('support_resistance', {}))}
Momentum: {_format_category(cat_scores.get('momentum', {}))}
Chart patterns: {_format_category(cat_scores.get('chart_patterns', {}))}
Candlesticks: {_format_category(cat_scores.get('candles', {}))}

In 3-4 sentences: What is the technical setup? Key levels? Trend strength? Pattern quality?
Is this a high-probability setup or a marginal one?"""

    return await hooks.llm_call("technical_analyst", state["symbol"], prompt, max_tokens=300)


async def volatility_analyst(state: AgentState, memory: str) -> str:
    cat_scores = state["analysis_result"].get("category_scores", {})
    iv = cat_scores.get("iv_analysis", {})

    # Conditional edge: skip if no meaningful IV data
    if not iv or iv.get("raw_score", 0) == 0:
        return "No IV data available for this symbol."

    prompt = f"""You are the Volatility Analyst for an options trading system.

Symbol: {state['symbol']}

IV Analysis: {_format_category(iv)}
GEX/DEX: {_format_category(cat_scores.get('gex_dex', {}))}
Vol Regime: {_format_category(cat_scores.get('volatility_regime', {}))}
Earnings-Adj IV: {_format_category(cat_scores.get('earnings_adj_iv', {}))}

In 3-4 sentences:
- Is IV cheap or expensive relative to realized vol?
- What structure does the vol regime favor (debit vs credit)?
- Any earnings or event risk embedded in IV?
- What's the GEX regime (dampen or amplify moves)?"""

    return await hooks.llm_call("volatility_analyst", state["symbol"], prompt, max_tokens=300)


async def sentiment_analyst_ollama(state: AgentState) -> str:
    """Uses local Ollama — cost-free, sufficient for sentiment summarization."""
    import httpx

    cat_scores = state["analysis_result"].get("category_scores", {})
    sentiment = cat_scores.get("sentiment", {})
    flow = cat_scores.get("options_flow", {})
    catalyst_flags = state["stage3_data"].get("catalyst_flags", {})

    # Conditional edge: skip if no news/sentiment data
    if not sentiment and not flow and not catalyst_flags:
        return "No sentiment or flow data available."

    prompt = f"""Summarize the sentiment picture for {state['symbol']} in 2-3 sentences.

Sentiment signals: {_format_category(sentiment)}
Options flow: {_format_category(flow)}
Catalyst flags: {catalyst_flags}

Is the sentiment bullish, bearish, or mixed? Any unusual activity?"""

    try:
        async with httpx.AsyncClient(timeout=20.0) as client:
            resp = await client.post(
                f"{settings.OLLAMA_BASE_URL}/api/generate",
                json={"model": settings.OLLAMA_CHAT_MODEL, "prompt": prompt, "stream": False},
            )
            data = resp.json()
            return data.get("response", "Sentiment data unavailable")
    except Exception as e:
        logger.debug(f"Ollama sentiment failed: {e}")
        return "Sentiment analysis unavailable (Ollama offline)"


# ── Trader + eval-optimizer ─────────────────────────────────────────────────

async def _run_trader(state: AgentState, combined_context: str) -> None:
    """
    Trader synthesis using Anthropic tool_use for structured output.
    Populates state['trader_thesis'] and state['conviction_score'].
    Falls back to text output if structured call fails.
    """
    prompt = f"""You are the Senior Options Trader. Synthesize the 4 analyst reports into a definitive trade thesis.

Symbol: {state['symbol']}
Quantitative score: {state['total_score']}/100
Direction: {state['direction']}
Vol regime: {state['vol_regime']}

=== ANALYST REPORTS ===
FUNDAMENTAL: {state['fundamental_report']}
TECHNICAL: {state['technical_report']}
VOLATILITY: {state['volatility_report']}
SENTIMENT: {state['sentiment_report']}

=== CROSS-STOCK CONTEXT ===
{state['cross_context'][:600]}

=== BEHAVIORAL DNA + LT CONTEXT ===
{combined_context[:700]}

Fill out the trade thesis tool with your analysis."""

    result = await hooks.llm_call_structured(
        agent_name="trader_agent",
        symbol=state["symbol"],
        prompt=prompt,
        output_schema=_TRADER_SCHEMA,
        tool_name="submit_trade_thesis",
        tool_description="Submit the structured trade thesis after synthesizing all analyst reports",
        model=settings.ANTHROPIC_TRADER_MODEL,
        max_tokens=600,
    )

    if result:
        try:
            thesis_obj = TraderThesis.model_validate(result)
            state["conviction_score"] = float(thesis_obj.conviction)
            state["trader_thesis"] = (
                f"THESIS: {thesis_obj.thesis}\n"
                f"EDGE: {thesis_obj.edge}\n"
                f"RISK: {thesis_obj.risk}\n"
                f"CONVICTION: {thesis_obj.conviction}\n"
                f"TIMING: {thesis_obj.timing}"
            )
        except Exception as e:
            logger.debug(f"TraderThesis validation failed: {e}")
            # Fallback: extract conviction from raw result
            state["conviction_score"] = float(result.get("conviction", 65))
            state["trader_thesis"] = str(result)
        return

    # Structured call failed — fall back to text
    fallback_response = await hooks.llm_call(
        "trader_agent", state["symbol"], prompt,
        model=settings.ANTHROPIC_TRADER_MODEL, max_tokens=500,
    )
    import re
    m = re.search(r"CONVICTION:\s*(\d+)", fallback_response)
    if m:
        state["conviction_score"] = float(m.group(1))
    state["trader_thesis"] = fallback_response


async def _run_trader_rebuttal(state: AgentState, challenges: list[str]) -> None:
    """
    Eval-optimizer loop: trader must respond to adversary challenges when risk_override > 15.

    If trader MAINTAINS: recover up to half the discount (adversary raised valid concerns
    but didn't invalidate the thesis). If trader REVISES: accept the revised conviction.
    This is one extra Opus call, only on hard-challenged trades (~25% of analyses).
    """
    challenges_str = "\n".join(f"- {c}" for c in challenges)
    prompt = f"""You are the Senior Options Trader. The adversary has challenged your thesis on {state['symbol']}.

YOUR ORIGINAL THESIS:
{state['trader_thesis'][:600]}

ADVERSARY CHALLENGES:
{challenges_str}

Respond directly to each challenge. Then decide:
- MAINTAIN: Your thesis holds despite the challenges. Explain why each concern is mitigated.
- REVISE: The challenges reveal a real flaw. Reduce your conviction accordingly.

Use the rebuttal tool to submit your response."""

    result = await hooks.llm_call_structured(
        agent_name="trader_rebuttal",
        symbol=state["symbol"],
        prompt=prompt,
        output_schema=_REBUTTAL_SCHEMA,
        tool_name="submit_rebuttal",
        tool_description="Submit trader rebuttal to adversary challenges",
        model=settings.ANTHROPIC_TRADER_MODEL,
        max_tokens=400,
    )

    if not result:
        return

    try:
        rebuttal = TraderRebuttal.model_validate(result)
    except Exception:
        return

    # Update thesis with rebuttal note
    state["trader_thesis"] += f"\n\n[ADVERSARY REBUTTAL — {rebuttal.stance}]: {rebuttal.response}"

    # Update conviction based on stance
    if rebuttal.stance == "MAINTAIN":
        # Trader maintained position: recover up to 50% of the adversary's discount
        # but only if revised_conviction is at or above current (post-discount) conviction
        recovered = min(
            state["conviction_score"] * 0.5,  # cap recovery at 50% of what we discounted
            max(0.0, rebuttal.revised_conviction - state["conviction_score"]),
        )
        state["conviction_score"] = min(100.0, state["conviction_score"] + recovered)
    else:
        # REVISE: take trader's own lower conviction
        state["conviction_score"] = float(rebuttal.revised_conviction)

    logger.info(
        f"[{state['symbol']}] Trader rebuttal: {rebuttal.stance} → conviction now {state['conviction_score']:.0f}"
    )


async def _run_risk_manager(state: AgentState) -> None:
    """Risk manager validation — Sonnet, structured output."""
    adversary_note = ""
    if state.get("adversary_report"):
        adversary_note = f"\nAdversary challenges: {state['adversary_report'][:300]}"

    prompt = f"""You are the Risk Manager. Review this proposed trade for {state['symbol']}.

Trader thesis: {state['trader_thesis'][:600]}
Total score: {state['total_score']}/100
Conviction: {state['conviction_score']}
Direction: {state['direction']}{adversary_note}

Risk checklist:
1. Is there a clear defined max-loss structure?
2. Is the setup confirmed (not a false breakout candidate)?
3. Is the trade sizing appropriate given conviction level?
4. Are there any portfolio correlation concerns?
5. Is there an earnings date risk within the trade window?

Submit your risk assessment using the tool."""

    result = await hooks.llm_call_structured(
        agent_name="risk_manager_agent",
        symbol=state["symbol"],
        prompt=prompt,
        output_schema=_RISK_SCHEMA,
        tool_name="submit_risk_assessment",
        tool_description="Submit the structured risk assessment with APPROVE/CONDITIONAL_APPROVE/REJECT verdict",
        model=settings.ANTHROPIC_MODEL,
        max_tokens=300,
    )

    if result:
        try:
            ra = RiskAssessment.model_validate(result)
            cond = f" Conditions: {ra.conditions}" if ra.conditions else ""
            state["risk_assessment"] = f"{ra.verdict}: {ra.reasoning}{cond}"
        except Exception:
            state["risk_assessment"] = str(result)
        return

    # Fallback to text
    state["risk_assessment"] = await hooks.llm_call(
        "risk_manager_agent", state["symbol"], prompt,
        model=settings.ANTHROPIC_MODEL, max_tokens=200,
    )


# ── Helpers ─────────────────────────────────────────────────────────────────

async def _run_adversary(state: AgentState, dna_context: str) -> dict:
    """Call the adversary agent (Ollama deepseek-r1). Non-blocking on failure."""
    try:
        from agents.adversary import run_adversary
        return await run_adversary(
            symbol=state["symbol"],
            trader_thesis=state["trader_thesis"],
            direction=state["direction"],
            total_score=state["total_score"],
            conviction_score=state["conviction_score"],
            category_scores=state["analysis_result"].get("category_scores", {}),
            dna_context=str(dna_context),
            vol_regime=state["vol_regime"],
        )
    except Exception as e:
        logger.debug(f"Adversary agent error for {state['symbol']}: {e}")
        return {"verdict": "PASS", "challenges": [], "risk_override": 0, "raw_response": ""}


async def options_selection_agent(state: AgentState, analysis: AnalysisResult) -> dict:
    from scoring.trade_structure import select_structure, TradeStructureInput

    iv_pct = analysis.iv_percentile or 50.0
    inp = TradeStructureInput(
        vol_regime=analysis.vol_regime,
        iv_percentile=iv_pct,
        direction=analysis.direction,
        total_score=analysis.total_score,
    )
    structure = select_structure(inp)

    try:
        from data.tradier import get_tradier
        tradier = get_tradier()
        chain = await tradier.get_best_chain(
            state["symbol"],
            min_dte=structure.dte_min,
            max_dte=structure.dte_max,
        )

        if chain:
            best = _find_strike_by_delta(chain, structure.target_delta, structure.direction)
            if best:
                return {
                    "strategy": structure.strategy,
                    "symbol": state["symbol"],
                    "expiry": best.get("expiration_date", ""),
                    "strike": best.get("strike"),
                    "option_type": best.get("option_type"),
                    "bid": best.get("bid"),
                    "ask": best.get("ask"),
                    "delta": best.get("greeks", {}).get("delta") if best.get("greeks") else None,
                    "dte_min": structure.dte_min,
                    "dte_max": structure.dte_max,
                    "target_delta": structure.target_delta,
                    "rationale": structure.rationale,
                }
    except Exception as e:
        logger.debug(f"Chain query failed in options_selection: {e}")

    return {
        "strategy": structure.strategy,
        "symbol": state["symbol"],
        "short_strike": structure.short_strike,
        "long_strike": structure.long_strike,
        "dte_min": structure.dte_min,
        "dte_max": structure.dte_max,
        "target_delta": structure.target_delta,
        "rationale": structure.rationale,
    }


def _build_order_ticket(state: AgentState, analysis: AnalysisResult) -> dict:
    from scoring.return_projection import compute_return_projection

    ts = state.get("trade_structure", {})
    bid  = ts.get("bid") or 0.0
    ask  = ts.get("ask") or 0.0
    mid  = round((bid + ask) / 2, 2) if bid and ask else bid or ask or 0.0

    iv_analysis_score = analysis.category_scores.get("iv_analysis", {})
    iv_pct = next(
        (float(s.get("iv_percentile") or s.get("value") or 50) for s in
         (iv_analysis_score.signals if hasattr(iv_analysis_score, "signals") else [])
         if s.get("name") == "iv_percentile"),
        50.0,
    )
    atm_iv = next(
        (float(s.get("value") or 0.30) / 100 for s in
         (iv_analysis_score.signals if hasattr(iv_analysis_score, "signals") else [])
         if s.get("name") == "atm_iv"),
        0.30,
    )

    strike_val = float(ts.get("strike") or ts.get("long_strike") or state.get("underlying_price") or 0)
    underlying = float(state.get("underlying_price") or strike_val or 100.0)
    dte = int(ts.get("dte_min") or ts.get("dte") or 21)

    projection = compute_return_projection(
        entry_option_price=mid or 1.0,
        underlying_price=underlying,
        strike=strike_val or underlying,
        dte=dte,
        iv=atm_iv,
        direction=state.get("direction", "neutral"),
        conviction_score=float(state.get("conviction_score") or 65),
        iv_percentile=iv_pct,
    )

    is_spread = "spread" in ts.get("strategy", "") or ts.get("strategy") == "iron_condor"
    max_profit = ts.get("max_profit") or (mid * 100 if not is_spread else None)
    max_loss   = ts.get("max_loss") or (mid * 100 if not is_spread else None)

    return {
        "symbol": state["symbol"],
        "strategy": ts.get("strategy", "TBD"),
        "direction": state["direction"],
        "expiry": ts.get("expiry", f"~{ts.get('dte_min',21)}-{ts.get('dte_max',45)} DTE"),
        "long_strike": ts.get("strike") or ts.get("long_strike"),
        "second_strike": ts.get("second_strike"),
        "option_type": ts.get("option_type"),
        "target_delta": ts.get("target_delta"),
        "bid": bid or None,
        "ask": ask or None,
        "mid": mid or None,
        "max_profit": max_profit,
        "max_loss": max_loss,
        "suggested_contracts": ts.get("suggested_contracts", 1),
        "target_exit": "50% max profit",
        "stop_loss": "2× credit received" if is_spread else "50% of debit paid",
        "conviction": state["conviction_score"],
        "thesis_summary": state["trader_thesis"][:300] if state["trader_thesis"] else "",
        "stream": projection.stream,
        "return_projection": projection.to_dict(),
        "validated_at": None,
    }


def _skip_result(symbol: str, analysis: AnalysisResult, stage3_item: dict, reason: str) -> dict:
    """Return a minimal result dict when we skip LLM analysis."""
    return {
        "symbol": symbol,
        "total_score": analysis.total_score,
        "conviction_score": 0.0,
        "direction": analysis.direction,
        "vol_regime": analysis.vol_regime,
        "iv_percentile": analysis.iv_percentile,
        "trade_thesis": f"SKIPPED: {reason}",
        "risk_assessment": "REJECT: Below minimum score threshold",
        "category_scores": analysis.to_dict().get("category_scores", {}),
        "catalyst_flags": stage3_item.get("catalyst_flags", {}),
        "order_ticket": {},
        "trade_structure": {},
        "raw_signals": analysis.raw_signals,
    }


async def _get_dna_context(symbol: str) -> str:
    try:
        from analysis.stock_dna import get_dna, format_dna_context
        dna = await get_dna(symbol)
        if dna and dna.data_quality_score > 20:
            return format_dna_context(dna)
        return ""
    except Exception:
        return ""


async def _get_lt_context(symbol: str) -> str:
    try:
        from analysis.lt_scoring import score_stock, format_lt_context
        lt = await score_stock(symbol=symbol)
        return format_lt_context(lt)
    except Exception:
        return ""


async def _retrieve_memory(symbol: str, analysis: AnalysisResult) -> str:
    try:
        from core.database import AsyncSessionLocal
        from sqlalchemy import text

        async with AsyncSessionLocal() as session:
            result = await session.execute(text("""
                SELECT lesson, r_multiple, regime, factors_that_worked, factors_that_failed
                FROM memory_entries
                WHERE regime = :regime OR sector IN (
                    SELECT sector FROM stocks WHERE symbol = :symbol
                )
                ORDER BY created_at DESC
                LIMIT 8
            """), {"regime": analysis.vol_regime, "symbol": symbol})
            rows = result.fetchall()

        if not rows:
            return "No relevant past trades in memory yet."

        lines = []
        for lesson, r_mult, regime, worked, failed in rows:
            lines.append(
                f"- [{regime}, R={r_mult:.1f}x] {lesson}"
                f"{' | WORKED: ' + ','.join(worked) if worked else ''}"
                f"{' | FAILED: ' + ','.join(failed) if failed else ''}"
            )
        return "\n".join(lines)
    except Exception:
        return "Memory unavailable"


# ── Context engineering helpers ─────────────────────────────────────────────

def _format_fundamental_context(cat: dict) -> str:
    """
    Structured context for fundamental analyst.
    Converts raw signal list into a decision-relevant table instead of raw JSON.
    """
    if not cat:
        return "No fundamental data available."

    signals = cat.get("signals", [])
    lines = []
    for s in signals:
        name = s.get("name", "")
        direction = s.get("direction", "")
        note = s.get("note", "")
        value = s.get("value", "")

        arrow = "→ BULLISH ✓" if direction == "bullish" else ("→ BEARISH ✗" if direction == "bearish" else "")
        val_str = f" ({value})" if value != "" else ""
        note_str = f": {note}" if note else ""
        lines.append(f"  {name}{val_str} {arrow}{note_str}")

    score = cat.get("raw_score", 0)
    overall = cat.get("direction", "neutral").upper()
    header = f"FUNDAMENTAL [{overall}, score={score:.1f}/10]"
    return header + "\n" + "\n".join(lines) if lines else header


def _format_category(cat: dict) -> str:
    """Compact format for non-fundamental categories."""
    if not cat:
        return "No data"
    signals = cat.get("signals", [])[:5]
    sig_str = "; ".join(
        f"{s.get('name','?')}={s.get('value', s.get('direction',''))}" for s in signals
    )
    return f"Score={cat.get('raw_score',0):.1f}/10 | {sig_str}"


def _find_strike_by_delta(chain: list[dict], target_delta: float, direction: str) -> dict | None:
    option_type = "C" if direction in ("bullish", "neutral") else "P"
    target_abs = abs(target_delta)
    candidates = [
        c for c in chain
        if c.get("option_type", "").upper() == option_type
        and (c.get("greeks", {}) or {}).get("delta") is not None
    ]
    if not candidates:
        return None
    candidates.sort(
        key=lambda c: abs(abs(float((c.get("greeks") or {}).get("delta") or 0)) - target_abs)
    )
    return candidates[0] if candidates else None
