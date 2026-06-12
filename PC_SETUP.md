# Trade Bot — PC Setup Guide for Claude Code

> **Read this first.** This document is for a fresh Claude Code session on a Linux PC.
> The app is already built and tested on a Mac. Your job is to clone it, resolve
> Linux-specific dependency issues, configure secrets, and get it running so that
> overnight background jobs (Ollama AI agents, nightly scans, sell-discipline monitors)
> can execute autonomously.
>
> The user (V) will provide API keys and answer questions. You have full permission to
> run `sudo` commands, edit config files, install packages, and start services.
> Do NOT commit .env files or secrets to git. Do NOT execute trades — this system
> is read-only and recommendation-only.

---

## What This App Is

**Trade Bot** is a private agentic trading research system for two users (V and N).
It covers three streams: options trades, swing trades, and long-term stock investments.

**It never executes trades.** It sends buy/sell recommendations to Discord. All
execution is manual by N through Robinhood.

**Stack:**
- **Frontend**: Next.js 14 (TypeScript) — dashboard, scanner UI, watchlist, LT pipeline
- **Backend**: FastAPI (Python 3.11) — LangGraph agents, scoring, analysis
- **Database**: PostgreSQL 15
- **Cache**: Redis 7
- **Local AI**: Ollama — llama3.1:8b (news/sentiment), deepseek-r1:7b (adversary/devil's advocate)
- **Cloud AI**: Anthropic Claude (Opus for trader synthesis, Sonnet for analysts)
- **GPU**: RTX 5080 (used for Ollama inference + future FAISS/LightGBM batch jobs)

**The goal for tonight:** App running on this PC so background jobs run overnight.
Frontend accessible at http://localhost:3000, backend at http://localhost:8000.

---

## What V Will Provide (Ask If Missing)

Ask V for these one at a time as you need them. They will be typed directly:

| Key | Where to get it | Used for |
|-----|----------------|---------|
| `ANTHROPIC_API_KEY` | console.anthropic.com | Claude AI (main brain) |
| `FMP_API_KEY` | financialmodelingprep.com | Fundamentals, LT scoring |
| `TRADIER_API_KEY` | tradier.com/user/profile/applications | Options data, paper trading |
| `ALPHA_VANTAGE_API_KEY` | alphavantage.co/support/#api-key | Technical indicators |
| `FRED_API_KEY` | fred.stlouisfed.org/docs/api/api_key.html | Macro data |
| `NEWS_API_KEY` | newsapi.org | News feeds |
| `DISCORD_WEBHOOK_URL` | Discord server settings → Integrations → Webhooks | Trade alerts |
| `SECRET_KEY` | Generate: `python3 -c "import secrets; print(secrets.token_hex(32))"` | JWT auth |
| `TRADIER_BASE_URL` | Set to `https://api.tradier.com/v1` (live) or `https://sandbox.tradier.com/v1` (paper) | |

**Optional (can leave blank for now):**
- `TWILIO_*` — SMS alerts (Discord is preferred anyway)

---

## Phase 0 — System Check (Do First, Takes 5 Min)

```bash
# GPU
nvidia-smi
# Expected: RTX 5080, Driver 550+, VRAM 16GB

# CUDA
nvcc --version
# Note the version — you'll need it for PyTorch

# Python
python3 --version
# Need 3.11+. If not: sudo apt install python3.11 python3.11-venv python3.11-dev

# Node
node --version
# Need 18+. If not: see Phase 1

# PostgreSQL
psql --version
# Need 15+

# Redis
redis-cli ping
# Should return: PONG

# Ollama
ollama list
# Should show llama3.1:8b, deepseek-r1:7b, nomic-embed-text
```

If anything is missing, handle it in Phase 1 before continuing.

---

## Phase 1 — Install Missing System Deps

Run only what's missing from Phase 0:

```bash
# Python 3.11 (if needed)
sudo apt update
sudo apt install -y python3.11 python3.11-venv python3.11-dev libpq-dev build-essential git curl wget

# Node.js 20 (if needed)
curl -fsSL https://deb.nodesource.com/setup_20.x | sudo -E bash -
sudo apt install -y nodejs

# PostgreSQL 15 (if needed)
sudo apt install -y postgresql-15 postgresql-client-15
sudo systemctl enable postgresql
sudo systemctl start postgresql

# Redis 7 (if needed)
sudo apt install -y redis-server
sudo systemctl enable redis-server
sudo systemctl start redis-server

# Ollama (if needed)
curl -fsSL https://ollama.com/install.sh | sh
# Then pull models:
ollama pull llama3.1:8b
ollama pull deepseek-r1:7b
ollama pull nomic-embed-text
```

**CUDA/PyTorch compatibility** (critical — get this wrong and GPU inference breaks):
```bash
# Check your CUDA version first
nvcc --version   # look for "release X.Y"

# CUDA 12.4 → use:
pip install torch==2.4.0 --index-url https://download.pytorch.org/whl/cu124

# CUDA 12.1 → use:
pip install torch==2.1.0 --index-url https://download.pytorch.org/whl/cu121

# CUDA 11.8 → use:
pip install torch==2.0.1 --index-url https://download.pytorch.org/whl/cu118

# Verify after install:
python3 -c "import torch; print(torch.cuda.is_available(), torch.version.cuda)"
# Must print: True  [your version]
```

---

## Phase 2 — Clone & Backend Setup

```bash
# Clone the repo
git clone https://github.com/[REPO_URL_HERE] ~/trade-bot
cd ~/trade-bot

# Create Python virtual environment
python3.11 -m venv backend/.venv
source backend/.venv/bin/activate

# Install backend dependencies
cd backend
pip install --upgrade pip
pip install -e ".[dev]"
```

**If you hit errors during pip install:**

```bash
# psycopg2 build fails:
pip install psycopg2-binary  # use binary, not source

# pandas-ta error:
pip install pandas-ta==0.3.14b0

# FAISS: pip installs CPU version silently — use this for GPU:
pip install faiss-gpu-cu12   # CUDA 12.x
# or: pip install faiss-cpu  # if GPU FAISS causes issues, CPU is fine for now

# lightgbm GPU support:
pip install lightgbm --config-settings=cmake.args="-DUSE_GPU=1"
# If that fails, CPU version is fine:
pip install lightgbm

# feedparser missing:
pip install feedparser

# pydantic-ai version conflict:
pip install pydantic-ai==0.0.14

# passlib bcrypt error:
pip install "passlib[bcrypt]>=1.7.4" "python-jose[cryptography]>=3.3.0"
```

---

## Phase 3 — Configure Environment

```bash
# Copy template and fill in keys
cp backend/.env.example backend/.env
# If no .env.example exists:
touch backend/.env
```

Edit `backend/.env` with the keys V provides. Minimum required to boot:

```env
DATABASE_URL=postgresql://tradebot:tradebot_secret@localhost:5432/trade_bot
POSTGRES_USER=tradebot
POSTGRES_PASSWORD=tradebot_secret
POSTGRES_DB=trade_bot
REDIS_URL=redis://localhost:6379/0
ANTHROPIC_API_KEY=sk-ant-...
ANTHROPIC_MODEL=claude-sonnet-4-6
ANTHROPIC_TRADER_MODEL=claude-opus-4-7
OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_CHAT_MODEL=llama3.1:8b
OLLAMA_ADVERSARY_MODEL=deepseek-r1:7b
OLLAMA_EMBED_MODEL=nomic-embed-text
FMP_API_KEY=...
TRADIER_API_KEY=...
TRADIER_BASE_URL=https://sandbox.tradier.com/v1
ALPHA_VANTAGE_API_KEY=...
FRED_API_KEY=...
NEWS_API_KEY=...
DISCORD_WEBHOOK_URL=https://discord.com/api/webhooks/...
SECRET_KEY=<generate with: python3 -c "import secrets; print(secrets.token_hex(32))">
APP_ENV=development
LOG_LEVEL=INFO
CORS_ORIGINS=["http://localhost:3000"]
```

---

## Phase 4 — Database Setup

```bash
# Create the database user and database
sudo -u postgres psql << 'EOF'
CREATE USER tradebot WITH PASSWORD 'tradebot_secret';
CREATE DATABASE trade_bot OWNER tradebot;
GRANT ALL PRIVILEGES ON DATABASE trade_bot TO tradebot;
\q
EOF

# Verify connection
psql postgresql://tradebot:tradebot_secret@localhost:5432/trade_bot -c "SELECT 1;"

# Run migrations in order
cd ~/trade-bot/backend
source .venv/bin/activate

psql postgresql://tradebot:tradebot_secret@localhost:5432/trade_bot -f db/migrations/001_init.sql 2>/dev/null || true
psql postgresql://tradebot:tradebot_secret@localhost:5432/trade_bot -f db/init.sql 2>/dev/null || true
psql postgresql://tradebot:tradebot_secret@localhost:5432/trade_bot -f db/migrations/004_stock_dna.sql
psql postgresql://tradebot:tradebot_secret@localhost:5432/trade_bot -f db/migrations/005_agent_monitor.sql
psql postgresql://tradebot:tradebot_secret@localhost:5432/trade_bot -f db/migrations/006_users_auth.sql

# Verify tables exist
psql postgresql://tradebot:tradebot_secret@localhost:5432/trade_bot -c "\dt"
# Should show: stocks, analysis_results, watchlist_tickers, portfolio_holdings,
#              stock_dna, agent_monitor_events, users, paper_trades, etc.
```

---

## Phase 5 — Frontend Setup

```bash
cd ~/trade-bot/frontend

# Install Node dependencies
npm install

# Create frontend env file
cat > .env.local << 'EOF'
NEXT_PUBLIC_API_URL=http://localhost:8000/api
EOF
```

---

## Phase 6 — Start Everything & Verify

Open 3 terminals (or use tmux):

**Terminal 1 — Backend:**
```bash
cd ~/trade-bot/backend
source .venv/bin/activate
uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```
Expected: `INFO: Application startup complete.`
If it crashes, read the error carefully — usually a missing .env key or import error.

**Terminal 2 — Frontend:**
```bash
cd ~/trade-bot/frontend
npm run dev
```
Expected: `▲ Next.js 14.x.x — Local: http://localhost:3000`

**Terminal 3 — Health checks:**
```bash
# Backend health
curl http://localhost:8000/health
# Expected: {"status":"ok","version":"0.1.0"}

# Frontend
curl -s -o /dev/null -w "%{http_code}" http://localhost:3000
# Expected: 200

# Ollama
curl http://localhost:11434/api/tags
# Expected: JSON with model list

# Redis
redis-cli ping
# Expected: PONG

# PostgreSQL
psql postgresql://tradebot:tradebot_secret@localhost:5432/trade_bot -c "SELECT COUNT(*) FROM users;"
# Expected: 0 (before user setup)
```

---

## Phase 7 — Create User Accounts

```bash
# Create V and N accounts (only works once, when users table is empty)
curl -X POST http://localhost:8000/auth/setup \
  -H "Content-Type: application/json" \
  -d '{"v_password": "ASK_V_FOR_THIS", "n_password": "ASK_V_FOR_THIS"}'

# Expected: {"status":"created","users":["v","n"]}
```

Ask V for the passwords before running this.

---

## Phase 8 — Seed Initial Data

```bash
# Add initial scanner universe stocks (top 50 to start, not full 5000)
# This is done via the API once the backend is running:
curl -X POST http://localhost:8000/api/stocks/seed-universe \
  -H "Content-Type: application/json" \
  -d '{"limit": 100}'

# Seed behavioral DNA for top stocks (runs in background, takes ~20 min)
curl -X POST http://localhost:8000/api/admin/seed-dna \
  -H "Content-Type: application/json" \
  -d '{"limit": 50}'

# Run first nightly scan manually to populate dashboard
curl -X POST http://localhost:8000/api/scanner/run
```

---

## Phase 9 — Verify Overnight Jobs

The scheduler starts automatically with the backend. Verify jobs are registered:

```bash
curl http://localhost:8000/api/admin/scheduler/jobs
```

Expected jobs:
- `nightly_scan` — 6:00 PM ET daily
- `nightly_dna` — 7:00 PM ET daily
- `position_monitor` — every 15 min weekdays 9:30–4:00 PM ET
- `catalyst_detector` — every 30 min weekdays
- `watchlist_refresh` — every 30 min weekdays
- `weekly_compaction` — Sunday 8 PM ET

**For overnight operation:** Leave the backend terminal running. Frontend can be stopped.
Backend handles all scheduled jobs — no separate cron needed.

To run as a background service (so it survives terminal close):
```bash
cd ~/trade-bot/backend
source .venv/bin/activate
nohup uvicorn main:app --host 0.0.0.0 --port 8000 > /tmp/tradebot.log 2>&1 &
echo "Backend PID: $!"
# To check logs: tail -f /tmp/tradebot.log
# To stop: kill <PID>
```

---

## Common Linux-Specific Errors

| Error | Fix |
|-------|-----|
| `psycopg2.OperationalError: could not connect` | Check PostgreSQL is running: `sudo systemctl status postgresql` |
| `redis.exceptions.ConnectionError` | Check Redis: `sudo systemctl status redis-server` |
| `ImportError: libGL.so.1` | `sudo apt install libgl1-mesa-glx` |
| `CUDA out of memory` | Ollama already manages VRAM — restart Ollama: `sudo systemctl restart ollama` |
| `faiss.StandardGpuResources` error | Fall back to CPU: `pip install faiss-cpu` and restart |
| `torch.cuda.is_available() = False` | CUDA/PyTorch version mismatch — redo Phase 1 PyTorch install |
| `Address already in use :8000` | `kill $(lsof -t -i:8000)` |
| `Address already in use :3000` | `kill $(lsof -t -i:3000)` |
| `ModuleNotFoundError` on startup | Re-run `pip install -e ".[dev]"` from backend dir with venv active |
| JWT `401 Not authenticated` on all routes | Run Phase 7 user creation, then POST /auth/login to get token |
| `yfinance` SSL errors | `pip install --upgrade certifi yfinance` |

---

## Architecture Reference (for debugging)

```
frontend (Next.js :3000)
    └── calls backend API at :8000/api/*

backend (FastAPI :8000)
    ├── /api/scanner/*     — stock scanning, LangGraph agent pipeline
    ├── /api/lt/*          — long-term investment scoring
    ├── /api/portfolio/*   — holdings import, user portfolio
    ├── /api/watchlist/*   — per-ticker agents
    ├── /api/trades/*      — paper trade management
    ├── /api/alerts/*      — Discord alert history
    ├── /auth/*            — JWT login/setup
    └── /health            — health check

agents (LangGraph)
    ├── graph.py           — main 6-stage pipeline (technical → fundamental → sentiment → options → adversary → trader)
    ├── watchlist_agent.py — per-ticker 30-min refresh
    ├── position_monitor.py — open trade monitoring
    └── catalyst.py        — news catalyst detection

AI models
    ├── Anthropic Claude Opus  — trader synthesis (most important calls)
    ├── Anthropic Claude Sonnet — 4 analyst agents in parallel
    ├── Ollama llama3.1:8b     — news classification, sentiment
    ├── Ollama deepseek-r1:7b  — adversary/devil's advocate (reasoning)
    └── Ollama nomic-embed-text — embeddings for vector search

data sources
    ├── Tradier     — live options chains, paper trading
    ├── FMP         — fundamentals, LT scoring, analyst estimates
    ├── Alpha Vantage — technical indicators
    ├── yfinance    — price history, behavioral DNA training
    ├── FRED        — macro data (VIX, yield curve, ISM PMI)
    └── NewsAPI + RSS — news feeds (Fed, market, macro)
```

---

## What To Do If Something Is Completely Broken

1. Check backend logs first: `tail -50 /tmp/tradebot.log` or terminal output
2. Check the specific import that fails: `python3 -c "from [module] import [thing]"`
3. Most issues are: missing .env key, wrong database URL, venv not activated, or Linux-specific package
4. The Mac version works perfectly — if in doubt, compare with `git diff origin/main`
5. Ask V — they have the working Mac setup and can tell you exactly what a working state looks like

---

*Last updated: June 2026 | App version: 0.1.0 | Built on MacBook Pro, targeting Linux (RTX 5080)*
