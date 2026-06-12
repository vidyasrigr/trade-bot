"""
Adversary Agent — devil's advocate before the risk manager.

Uses deepseek-r1:7b (reasoning model) via Ollama — free, local, zero API cost.
Looks for contradictions, structural misfits, and DNA-flagged risks the trader
may have glossed over. Outputs a discount to apply to the conviction score.

Output is validated with AdversaryVerdict (Pydantic) — retries up to 3× so
deepseek-r1's occasionally messy JSON never crashes the pipeline.

Model fallback: deepseek-r1:7b → llama3.1:8b if deepseek not available.
"""

from __future__ import annotations

import json
import re

import httpx
from loguru import logger
from pydantic import ValidationError

from agents.output_models import AdversaryVerdict
from core.config import settings


async def _ollama_call(prompt: str, model: str) -> str:
    try:
        async with httpx.AsyncClient(timeout=45.0) as client:
            resp = await client.post(
                f"{settings.OLLAMA_BASE_URL}/api/generate",
                json={"model": model, "prompt": prompt, "stream": False},
            )
            resp.raise_for_status()
            return resp.json().get("response", "")
    except Exception as e:
        logger.debug(f"Ollama adversary call failed ({model}): {e}")
        return ""


def _strip_think(text: str) -> str:
    return re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL).strip()


def _extract_verdict(response: str) -> AdversaryVerdict | None:
    """Try to parse AdversaryVerdict from a raw LLM response. Returns None on failure."""
    clean = _strip_think(response)
    json_match = re.search(r"\{[\s\S]*\}", clean)
    if not json_match:
        return None
    try:
        data = json.loads(json_match.group())
        return AdversaryVerdict.model_validate(data)
    except (json.JSONDecodeError, ValidationError):
        return None


async def run_adversary(
    symbol: str,
    trader_thesis: str,
    direction: str,
    total_score: float,
    conviction_score: float,
    category_scores: dict,
    dna_context: str,
    vol_regime: str,
) -> dict:
    """
    Challenge the trader thesis. Returns a dict compatible with the existing pipeline:
      {
        "verdict":        "PASS" | "CHALLENGE",
        "challenges":     ["specific concern 1", ...],
        "risk_override":  0-30,
        "raw_response":   str,
      }

    Retries up to 3× with Pydantic validation before falling back to heuristics.
    """
    cat_lines = []
    for name, cat in list(category_scores.items())[:12]:
        s = cat.get("raw_score", 5)
        d = cat.get("direction", "neutral")
        cat_lines.append(f"  {name}: {s:.1f}/10 [{d}]")
    cat_summary = "\n".join(cat_lines)

    prompt = f"""You are a professional adversarial risk analyst. Your ONLY job is to find flaws in this proposed trade.
Be ruthlessly skeptical. Do NOT agree with the trader just because a score is high.

=== TRADE PROPOSAL ===
Symbol: {symbol}
Direction: {direction}
Quant score: {total_score:.0f}/100
Trader conviction: {conviction_score:.0f}/100
Vol regime: {vol_regime}

=== TRADER THESIS ===
{trader_thesis[:600]}

=== CATEGORY SCORES ===
{cat_summary}

=== BEHAVIORAL DNA ===
{dna_context[:400] if dna_context else "Not available"}

=== YOUR JOB ===
Check ALL of the following for flaws:
1. Does proposed direction CONTRADICT any category scoring against it?
2. Earnings date risk within the trade window?
3. High IVR + buying debit = structural mistake
4. Low IVR + selling premium = structural mistake
5. DNA shows this stock historically sells off on this exact setup?
6. Is conviction inflated — are any signals weak or stale?
7. Any other red flags

Respond with this EXACT JSON (no other text, no markdown):
{{
  "verdict": "PASS" or "CHALLENGE",
  "challenges": ["specific concern 1", "specific concern 2"],
  "risk_override": 0
}}

If no real flaws: verdict=PASS, challenges=[], risk_override=0.
If serious flaws: verdict=CHALLENGE, list each one, risk_override=10-30."""

    raw = ""

    # Try deepseek-r1 first (better reasoning), fallback to llama3.1
    for model in [settings.OLLAMA_ADVERSARY_MODEL, settings.OLLAMA_CHAT_MODEL]:
        raw = await _ollama_call(prompt, model)
        if raw:
            break

    if not raw:
        logger.debug(f"Adversary agent unavailable for {symbol} (Ollama offline)")
        return {"verdict": "PASS", "challenges": [], "risk_override": 0, "raw_response": ""}

    # Retry up to 3 times with Pydantic validation
    verdict: AdversaryVerdict | None = None
    for attempt in range(3):
        verdict = _extract_verdict(raw)
        if verdict is not None:
            break
        if attempt < 2:
            # Ask again with a stricter prompt
            retry_prompt = (
                "You must respond with ONLY valid JSON matching this schema:\n"
                '{"verdict": "PASS" or "CHALLENGE", "challenges": [...], "risk_override": 0-30}\n\n'
                f"Previous response was not valid JSON. Original trade: {symbol} {direction} score={total_score:.0f}\n"
                "Respond with JSON only, no other text."
            )
            raw = await _ollama_call(retry_prompt, settings.OLLAMA_ADVERSARY_MODEL or settings.OLLAMA_CHAT_MODEL)

    if verdict is None:
        # Final heuristic fallback
        has_challenge = "CHALLENGE" in _strip_think(raw).upper()
        return {
            "verdict": "CHALLENGE" if has_challenge else "PASS",
            "challenges": [_strip_think(raw)[:200]] if has_challenge else [],
            "risk_override": 10 if has_challenge else 0,
            "raw_response": raw,
        }

    return {
        "verdict": verdict.verdict,
        "challenges": verdict.challenges,
        "risk_override": verdict.risk_override,
        "raw_response": raw,
    }
