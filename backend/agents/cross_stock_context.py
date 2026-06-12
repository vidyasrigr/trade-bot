"""
Builds cross-stock context document for Claude before individual analysis.
Claude sees all Stage 3 survivors simultaneously — enables sector rotation detection.
"""

from core.config import settings
from anthropic import AsyncAnthropic


async def build_cross_stock_context(stage3_results: list[dict]) -> str:
    """
    Summarizes all Stage 3 survivors into a compact cross-stock context.
    Claude uses this to detect: sector clustering, contradictions, mean-reversion risk.
    """
    if not stage3_results:
        return "No cross-stock context available."

    # Build summary table
    lines = [f"=== {len(stage3_results)} STOCKS REACHED STAGE 3 ===\n"]
    lines.append("Symbol | Sector | Score | Direction | Top Signals | Catalyst")
    lines.append("-" * 80)

    sector_counts: dict[str, int] = {}
    for item in stage3_results:
        symbol = item.get("symbol", "?")
        sector = item.get("stage1_data", {}).get("sector", "?")
        score  = item.get("total_score", 0) or item.get("adjusted_score", 0)
        direction = item.get("direction", "?")
        flags = item.get("catalyst_flags", {})
        catalyst = flags.get("event_type", "") if isinstance(flags, dict) else str(flags)[:30]

        sector_counts[sector] = sector_counts.get(sector, 0) + 1

        lines.append(f"{symbol:6} | {sector[:12]:12} | {score:5.1f} | {direction:8} | {catalyst[:20]}")

    # Identify sector clusters
    clusters = [f"{sector}×{count}" for sector, count in sorted(sector_counts.items(), key=lambda x: -x[1]) if count >= 2]
    if clusters:
        lines.append(f"\nSECTOR CLUSTERS: {', '.join(clusters)}")
        lines.append("→ Multiple hits in same sector may indicate rotation signal, not independent setups")

    # Flag any massive YTD gainers (mean-reversion risk)
    context_str = "\n".join(lines)

    # Ask Claude to synthesize cross-stock patterns (one quick call, small prompt)
    try:
        client = AsyncAnthropic(api_key=settings.ANTHROPIC_API_KEY)
        response = await client.messages.create(
            model=settings.ANTHROPIC_MODEL,
            max_tokens=300,
            messages=[{
                "role": "user",
                "content": f"""You are reviewing {len(stage3_results)} stocks that passed the signal funnel.
In 3-4 sentences, identify:
1. Any sector rotation patterns
2. Contradictory signals (e.g., 3 semis bullish but macro bearish)
3. Mean-reversion risk (anything up 200%+ recently?)
4. The single highest-conviction theme across these stocks

Context:
{context_str[:1000]}"""
            }]
        )
        synthesis = response.content[0].text
    except Exception:
        synthesis = "Cross-stock synthesis unavailable"

    return context_str + f"\n\n=== CLAUDE CROSS-STOCK SYNTHESIS ===\n{synthesis}"
