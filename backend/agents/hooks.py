"""
LLM call hooks: pre-call context injection, post-call monitoring, error fallback.

Every Claude call in the pipeline uses llm_call() or llm_call_structured()
instead of calling the Anthropic client directly. This gives us:

  Pre-hook  — prompt is fully formed before the call (no implicit state)
  Post-hook — agent_monitor.record fires non-blocking after every call
  Error-hook — RateLimitError / APIStatusError triggers model fallback chain:
               Opus → Sonnet → Haiku (each step only if the one above fails)
"""

from __future__ import annotations

import asyncio
import json
import time
from typing import Any

import httpx
from anthropic import (
    AsyncAnthropic, RateLimitError, APIStatusError, AuthenticationError,
)
from loguru import logger

from core.config import settings

# Anthropic is intentionally optional (expensive). EVERY agent LLM call falls back
# to a local Ollama model (settings.OLLAMA_FALLBACK_MODEL) when Anthropic is
# unusable — either no API key OR an invalid/expired key (401). The first auth
# failure flips _anthropic_disabled so we stop retrying a known-bad key (no
# latency, no log spam) and route everything to Ollama. Keeps the whole pipeline
# — trader, analysts, risk manager — working at $0.
_USE_ANTHROPIC = bool(settings.ANTHROPIC_API_KEY)
_anthropic_disabled = not _USE_ANTHROPIC
_client = AsyncAnthropic(api_key=settings.ANTHROPIC_API_KEY) if _USE_ANTHROPIC else None
if _anthropic_disabled:
    logger.warning(
        f"ANTHROPIC_API_KEY not set — agent LLM calls use Ollama "
        f"'{settings.OLLAMA_FALLBACK_MODEL}'"
    )


def _disable_anthropic(reason: str) -> None:
    """Flip to Ollama-only after an auth failure — logged once."""
    global _anthropic_disabled
    if not _anthropic_disabled:
        _anthropic_disabled = True
        logger.warning(
            f"Anthropic disabled ({reason}) — all further LLM calls use Ollama "
            f"'{settings.OLLAMA_FALLBACK_MODEL}'"
        )

# Fallback chain: if a model fails, try the next one down
_FALLBACK: dict[str, str] = {
    settings.ANTHROPIC_TRADER_MODEL: settings.ANTHROPIC_MODEL,    # opus → sonnet
    settings.ANTHROPIC_MODEL: "claude-haiku-4-5-20251001",         # sonnet → haiku
}


async def _ollama_generate(prompt: str, max_tokens: int = 500,
                           system: str | None = None, json_mode: bool = False) -> str:
    """Local-model completion via Ollama (the Anthropic-off fallback)."""
    payload: dict[str, Any] = {
        "model": settings.OLLAMA_FALLBACK_MODEL,
        "prompt": prompt,
        "stream": False,
        # Suppress chain-of-thought (reasoning models otherwise leak <think> text
        # and can burn the whole token budget before answering) and give a sane
        # floor so short calls still get a complete answer.
        "think": False,
        "options": {"num_predict": max(max_tokens, 256)},
    }
    if system:
        payload["system"] = system
    if json_mode:
        payload["format"] = "json"
    async with httpx.AsyncClient(timeout=180.0) as client:
        resp = await client.post(f"{settings.OLLAMA_BASE_URL}/api/generate", json=payload)
        return resp.json().get("response", "") if resp.status_code == 200 else ""


async def _ollama_text(agent_name: str, symbol: str, prompt: str,
                       max_tokens: int, system: str | None) -> str:
    start = time.monotonic()
    response = await _ollama_generate(prompt, max_tokens, system)
    elapsed = (time.monotonic() - start) * 1000
    asyncio.create_task(_post_hook(agent_name, settings.OLLAMA_FALLBACK_MODEL,
                                   symbol, elapsed, response, 0, 0))
    return response or "Analysis unavailable (Ollama fallback returned empty)"


async def _ollama_structured(agent_name: str, symbol: str, prompt: str,
                             output_schema: dict, max_tokens: int) -> dict:
    start = time.monotonic()
    schema_prompt = (
        prompt + "\n\nRespond ONLY with a single JSON object matching this schema "
        f"(fill every field): {json.dumps(output_schema)}\nNo prose, no markdown fences."
    )
    raw = await _ollama_generate(schema_prompt, max_tokens, json_mode=True)
    try:
        result = json.loads(raw) if raw else {}
    except json.JSONDecodeError:
        result = {}
    if not isinstance(result, dict):
        result = {}
    elapsed = (time.monotonic() - start) * 1000
    asyncio.create_task(_post_hook(agent_name, settings.OLLAMA_FALLBACK_MODEL,
                                   symbol, elapsed, str(result), 0, 0))
    return result


async def llm_call(
    agent_name: str,
    symbol: str,
    prompt: str,
    model: str | None = None,
    max_tokens: int = 400,
    system: str | None = None,
) -> str:
    """
    Single Claude call with pre/post/error hooks.

    Falls back down the model chain on RateLimitError or APIStatusError.
    Post-hook fires agent_monitor.record non-blocking regardless of outcome.
    """
    if _anthropic_disabled:
        return await _ollama_text(agent_name, symbol, prompt, max_tokens, system)

    primary = model or settings.ANTHROPIC_MODEL
    fallback = _FALLBACK.get(primary)

    start = time.monotonic()
    used_model = primary
    response = ""
    input_tokens = output_tokens = 0

    for attempt_model in filter(None, [primary, fallback]):
        try:
            response, input_tokens, output_tokens = await _do_call(prompt, attempt_model, max_tokens, system)
            used_model = attempt_model
            break
        except AuthenticationError as e:
            _disable_anthropic(type(e).__name__)
            return await _ollama_text(agent_name, symbol, prompt, max_tokens, system)
        except (RateLimitError, APIStatusError) as e:
            if attempt_model == primary and fallback:
                logger.warning(
                    f"[{agent_name}/{symbol}] {type(e).__name__} on {primary}, "
                    f"falling back to {fallback}"
                )
                continue
            logger.error(f"[{agent_name}/{symbol}] Claude call failed on {attempt_model}: {e}")
            response = f"Analysis unavailable: {type(e).__name__}"
            used_model = attempt_model
            break
        except Exception as e:
            logger.error(f"[{agent_name}/{symbol}] Unexpected error on {attempt_model}: {e}")
            response = f"Analysis unavailable: {type(e).__name__}"
            used_model = attempt_model
            break

    elapsed = (time.monotonic() - start) * 1000
    asyncio.create_task(_post_hook(agent_name, used_model, symbol, elapsed, response,
                                   input_tokens, output_tokens))
    return response


async def llm_call_structured(
    agent_name: str,
    symbol: str,
    prompt: str,
    output_schema: dict,
    tool_name: str,
    tool_description: str,
    model: str | None = None,
    max_tokens: int = 500,
) -> dict:
    """
    Claude call that forces structured JSON output via Anthropic tool_use.

    tool_choice={"type":"tool","name":tool_name} guarantees the model fills
    every field in output_schema. Retries once on the fallback model if needed.
    Returns empty dict on complete failure — callers must handle this gracefully.
    """
    if _anthropic_disabled:
        return await _ollama_structured(agent_name, symbol, prompt, output_schema, max_tokens)

    primary = model or settings.ANTHROPIC_MODEL
    fallback = _FALLBACK.get(primary)

    start = time.monotonic()
    result: dict = {}
    used_model = primary
    input_tokens = output_tokens = 0

    for attempt_model in filter(None, [primary, fallback]):
        try:
            msg = await _client.messages.create(
                model=attempt_model,
                max_tokens=max_tokens,
                tools=[{
                    "name": tool_name,
                    "description": tool_description,
                    "input_schema": output_schema,
                }],
                tool_choice={"type": "tool", "name": tool_name},
                messages=[{"role": "user", "content": prompt}],
            )
            input_tokens = msg.usage.input_tokens
            output_tokens = msg.usage.output_tokens
            for block in msg.content:
                if block.type == "tool_use" and block.name == tool_name:
                    result = dict(block.input)
                    used_model = attempt_model
                    break
            if result:
                break
        except AuthenticationError as e:
            _disable_anthropic(type(e).__name__)
            return await _ollama_structured(agent_name, symbol, prompt, output_schema, max_tokens)
        except (RateLimitError, APIStatusError) as e:
            if attempt_model == primary and fallback:
                logger.warning(
                    f"[{agent_name}/{symbol}] {type(e).__name__} on {primary}, "
                    f"retrying structured call with {fallback}"
                )
                continue
            logger.error(f"[{agent_name}/{symbol}] Structured call failed: {e}")
            break
        except Exception as e:
            logger.error(f"[{agent_name}/{symbol}] Structured call unexpected error: {e}")
            break

    elapsed = (time.monotonic() - start) * 1000
    asyncio.create_task(_post_hook(agent_name, used_model, symbol, elapsed, str(result),
                                   input_tokens, output_tokens))
    return result


async def _do_call(
    prompt: str,
    model: str,
    max_tokens: int,
    system: str | None,
) -> tuple[str, int, int]:
    """Returns (text, input_tokens, output_tokens)."""
    kwargs: dict[str, Any] = {
        "model": model,
        "max_tokens": max_tokens,
        "messages": [{"role": "user", "content": prompt}],
    }
    if system:
        kwargs["system"] = [{"type": "text", "text": system}]
    msg = await _client.messages.create(**kwargs)
    return msg.content[0].text, msg.usage.input_tokens, msg.usage.output_tokens


async def _post_hook(
    agent_name: str,
    model: str,
    symbol: str,
    elapsed_ms: float,
    response: str,
    input_tokens: int = 0,
    output_tokens: int = 0,
) -> None:
    try:
        from agents.agent_monitor import record
        await record(agent_name, model, symbol, elapsed_ms, response,
                     input_tokens=input_tokens, output_tokens=output_tokens)
    except Exception:
        pass
