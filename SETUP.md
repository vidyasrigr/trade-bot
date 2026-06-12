# Options Trading Bot — Setup Guide

## Quick Start (5 steps)

### 1. Copy and fill in env files
```bash
cp backend/.env.example backend/.env
cp frontend/.env.local.example frontend/.env.local
# Edit backend/.env with your API keys:
# ANTHROPIC_API_KEY, TRADIER_API_KEY, ALPHA_VANTAGE_API_KEY, FRED_API_KEY, NEWS_API_KEY
```

### 2. Start the database
```bash
docker-compose up -d
# Waits ~10 seconds for TimescaleDB + pgvector to initialize
```

### 3. Install and start backend
```bash
cd backend
pip install uv
uv sync
uv run uvicorn main:app --reload --port 8000
```

### 4. Install and start frontend
```bash
cd frontend
npm install
npm run dev
# Opens at http://localhost:3000
```

### 5. Run your first scan
- Open http://localhost:3000/scanner
- Click "Run Scan"
- Wait ~5-10 min for Stage 1-3 (free, no LLM)
- Stage 4 will call Claude (~15 API calls)

---

## Required API Keys

| Service | Free Tier | URL |
|---------|-----------|-----|
| Anthropic (Claude) | $5 free credit | platform.anthropic.com |
| Tradier (paper trading) | Free sandbox | developer.tradier.com |
| Alpha Vantage | 25 calls/day free | alphavantage.co |
| FRED | Free | fred.stlouisfed.org/docs/api |
| NewsAPI | 100 calls/day free | newsapi.org |
| FMP (analyst targets) | 250 calls/day free | financialmodelingprep.com |

---

## Integrating Ollama (RTX 5080 PC)

After pushing to GitHub and pulling on your PC:

```bash
# On your RTX 5080 PC
ollama pull llama3.1:8b
ollama pull nomic-embed-text

# Update backend/.env
OLLAMA_BASE_URL=http://localhost:11434
```

The system will automatically use Ollama for:
- News filtering (Stage 3 of funnel)
- Sentiment analysis (cheaper than Claude)
- RAG embeddings for memory
- Chart pattern narration tooltips

---

## Architecture

```
frontend/           Next.js 14 (App Router) + TypeScript + Tailwind
backend/
  data/             Market data clients (Tradier, yfinance, Alpha Vantage, FRED)
  analysis/         20 category analyzers (all parallel)
  scoring/          Deterministic engines (trade structure, portfolio risk, IC tracker)
  agents/           LangGraph pipeline (4 analysts → trader → risk mgr → options selector)
  api/              FastAPI routes + SSE streaming
  backtest/         Cold-start seeding + backtester
docker-compose.yml  PostgreSQL 15 + TimescaleDB + pgvector
```

## Key URLs

- Scanner: http://localhost:3000/scanner
- Analysis: http://localhost:3000/analysis/NVDA
- Trades: http://localhost:3000/trades
- Journal: http://localhost:3000/journal
- Politics: http://localhost:3000/politics
- API docs: http://localhost:8000/docs
