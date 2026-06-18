# API Keys — Trade Bot Setup

All keys are configured in `/home/vi/Projects/Trade Bot/API_KEYS.md` except Anthropic & Discord (shared after paper testing).

| # | Key | Source | Status |
|---|-----|--------|--------|
| 1 | `ANTHROPIC_API_KEY` | TBD (shared after paper testing) | — |
| 2 | `DISCORD_WEBHOOK_URL` | TBD (shared after paper testing) | — |
| 3 | `SECRET_KEY` | API_KEYS.md | ✓ |
| 4 | `FMP_API_KEY` | API_KEYS.md | ✓ |
| 5 | `MARKETDATA_API_KEY` | API_KEYS.md | ✓ |
| 6 | `ALPHA_VANTAGE_API_KEY` | API_KEYS.md | ✓ |
| 7 | `FRED_API_KEY` | API_KEYS.md | ✓ |
| 8 | `NEWS_API_KEY` | API_KEYS.md | ✓ |

---

## Notes

- **Tradier removed** — replaced by MarketData.app (MARKETDATA_API_KEY)
- **DATABASE_URL**, **REDIS_URL**, **OLLAMA_***: Auto-configured during setup
- **Twilio** (SMS): Optional — Discord preferred
