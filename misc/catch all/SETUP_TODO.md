# Options Trading Bot — Complete Setup Timeline

> **Who does what:** V = handles technical setup. N = handles trading decisions + Robinhood CSV import.
> All times are realistic minimums — don't be generous with yourself.

> **Claude Code on the Linux PC:** Once the project is cloned, open it in Claude Code and it can run most of Phase 0–3 for you. Just say "help me complete Phase 0 setup" and it will run the bash commands, fix errors, edit configs, and check output. Commands requiring `sudo` or interactive prompts (database password, auth flows) will need your approval or the `! command` syntax. Think of it as pair-programming the setup.

---

## Phase 0 — Linux PC: GPU + System Setup
*Do this first. Everything else breaks if CUDA isn't right.*

| # | Task | Who | Time | Day | Command / Notes |
|---|------|-----|------|-----|-----------------|
| 0.1 | Check GPU driver | V | 2 min | Day 0 | `nvidia-smi` — note driver version and VRAM |
| 0.2 | Check CUDA toolkit version | V | 1 min | Day 0 | `nvcc --version` — note the version (e.g. 12.1) |
| 0.3 | If CUDA mismatch: install correct toolkit | V | 20 min | Day 0 | `sudo apt install cuda-toolkit-12-1` (match your driver) |
| 0.4 | Install system deps | V | 5 min | Day 0 | `sudo apt install -y python3.11 python3.11-venv python3.11-dev libpq-dev build-essential git curl` |
| 0.5 | Install PostgreSQL 15 | V | 5 min | Day 0 | `sudo apt install postgresql-15 postgresql-client-15` |
| 0.6 | Install Redis 7 | V | 3 min | Day 0 | `sudo apt install redis-server && sudo systemctl enable redis-server` |
| 0.7 | Install Node.js 20 (for frontend) | V | 5 min | Day 0 | `curl -fsSL https://deb.nodesource.com/setup_20.x \| sudo -E bash - && sudo apt install nodejs` |
| 0.8 | Install Ollama | V | 5 min | Day 0 | `curl -fsSL https://ollama.com/install.sh \| sh` |
| 0.9 | Pull Ollama models | V | 15 min | Day 0 | `ollama pull llama3.1:8b && ollama pull deepseek-r1:7b && ollama pull nomic-embed-text` |
| 0.10 | Verify Ollama works | V | 1 min | Day 0 | `ollama run llama3.1:8b "hello"` |

### CUDA Compatibility Cheat Sheet (saves you hours of pain)
```
CUDA 12.1 → torch 2.1.x  → pip install torch==2.1.0 --index-url https://download.pytorch.org/whl/cu121
CUDA 12.4 → torch 2.4.x  → pip install torch==2.4.0 --index-url https://download.pytorch.org/whl/cu124
CUDA 11.8 → torch 2.0.x  → pip install torch==2.0.1 --index-url https://download.pytorch.org/whl/cu118

# VERIFY after install:
python -c "import torch; print(torch.cuda.is_available(), torch.version.cuda)"
# Must print: True  12.1 (or your version)
```

### Common Linux dependency failures:
```bash
# psycopg2 fails → need libpq-dev
sudo apt install libpq-dev

# pandas-ta import error → pin the version
pip install pandas-ta==0.3.14b0

# FAISS-GPU: use conda, not pip (pip installs CPU version silently)
conda install -c pytorch -c nvidia faiss-gpu=1.7.4 cuda-version=12.1
# OR if not using conda:
pip install faiss-gpu-cu12   # CUDA 12.x wheels

# feedparser missing
pip install feedparser

# uvloop issues on some Linux
pip install uvloop==0.19.0

# cryptography/rust build failures
pip install --upgrade pip setuptools wheel
```

---

## Phase 1 — Project Setup
| # | Task | Who | Time | Day | Command / Notes |
|---|------|-----|------|-----|-----------------|
| 1.1 | Clone repo to Linux PC | V | 2 min | Day 0 | `git clone <repo> && cd Options` |
| 1.2 | Create Python venv (must be 3.11) | V | 2 min | Day 0 | `python3.11 -m venv venv && source venv/bin/activate` |
| 1.3 | Install PyTorch with correct CUDA (see above) | V | 10 min | Day 0 | Match your CUDA version exactly |
| 1.4 | Install all other requirements | V | 10 min | Day 0 | `pip install -r backend/requirements.txt` |
| 1.5 | Install FAISS-GPU | V | 5 min | Day 0 | See cheat sheet above |
| 1.6 | Install frontend deps | V | 3 min | Day 0 | `cd frontend && npm install` |
| 1.7 | Copy env template | V | 1 min | Day 0 | `cp backend/.env.example backend/.env` |
| 1.8 | Verify Python imports | V | 2 min | Day 0 | `python -c "import torch, pandas, fastapi, anthropic, yfinance; print('OK')"` |

---

## Phase 2 — API Accounts (all in one sitting)
*Get all keys before you start the server. Takes ~45 min total.*

| # | Task | Who | Time | Day | URL / Notes |
|---|------|-----|------|-----|-------------|
| 2.1 | Anthropic API key | V | 5 min | Day 0 | console.anthropic.com → API Keys → Create key. Add $20-50 credit to start. |
| 2.2 | FMP account ($14/month) | V | 5 min | Day 0 | financialmodelingprep.com → Pricing → Starter plan. Get API key from dashboard. |
| 2.3 | Tradier sandbox account (free) | V | 10 min | Day 0 | developer.tradier.com → Register → Generate sandbox token. No real money yet. |
| 2.4 | FRED API key (free) | V | 3 min | Day 0 | fred.stlouisfed.org/docs/api/api_key.html → Request API Key |
| 2.5 | Discord: create server + webhook | V | 10 min | Day 0 | Discord → + New Server → Settings → Integrations → Webhooks → New Webhook → Copy URL |
| 2.6 | (Optional) Twilio SMS | V | 10 min | Day 0 | twilio.com → free trial gives $15 credit. Only if you want SMS fallback. |
| 2.7 | Fill in backend/.env | V | 10 min | Day 0 | See .env template below |

### .env file — all required keys:
```bash
# Database
DATABASE_URL=postgresql://options:your_password@localhost:5432/options_trading

# Redis
REDIS_URL=redis://localhost:6379/0

# LLMs
ANTHROPIC_API_KEY=sk-ant-...
ANTHROPIC_MODEL=claude-sonnet-4-6
ANTHROPIC_TRADER_MODEL=claude-opus-4-7

# Ollama (local — no key needed)
OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_CHAT_MODEL=llama3.1:8b
OLLAMA_ADVERSARY_MODEL=deepseek-r1:7b
OLLAMA_EMBED_MODEL=nomic-embed-text

# Market data
TRADIER_API_KEY=your_sandbox_token
TRADIER_BASE_URL=https://sandbox.tradier.com/v1
FRED_API_KEY=your_fred_key
FMP_API_KEY=your_fmp_key

# Alerts
DISCORD_WEBHOOK_URL=https://discord.com/api/webhooks/...

# App
APP_ENV=development
CORS_ORIGINS=["http://localhost:3000"]
PAPER_PORTFOLIO_VALUE=150000.0

# Trading params (leave defaults for now)
KELLY_FRACTION=0.50
```

---

## Phase 3 — Database Setup
| # | Task | Who | Time | Day | Command |
|---|------|-----|------|-----|---------|
| 3.1 | Create PostgreSQL user + database | V | 3 min | Day 0 | `sudo -u postgres psql -c "CREATE USER options WITH PASSWORD 'your_password';"` then `CREATE DATABASE options_trading OWNER options;` |
| 3.2 | Run base migration | V | 1 min | Day 0 | `psql -U options -d options_trading -f backend/db/migrations/init.sql` |
| 3.3 | Run DNA + LT migration | V | 1 min | Day 0 | `psql -U options -d options_trading -f backend/db/migrations/004_stock_dna.sql` |
| 3.4 | Run agent monitor migration | V | 1 min | Day 0 | `psql -U options -d options_trading -f backend/db/migrations/005_agent_monitor.sql` |
| 3.5 | Verify tables exist | V | 1 min | Day 0 | `psql -U options -d options_trading -c "\dt"` — should show 15+ tables |
| 3.6 | Start Redis | V | 1 min | Day 0 | `sudo systemctl start redis-server && redis-cli ping` → should print PONG |

---

## Phase 4 — First Server Start + Validation
| # | Task | Who | Time | Day | Notes |
|---|------|-----|------|-----|-------|
| 4.1 | Start backend | V | 1 min | Day 1 | `cd backend && uvicorn main:app --host 0.0.0.0 --port 8000 --reload` |
| 4.2 | Health check | V | 1 min | Day 1 | `curl http://localhost:8000/health` → `{"status":"ok"}` |
| 4.3 | Start frontend | V | 1 min | Day 1 | `cd frontend && npm run dev` → opens on localhost:3000 |
| 4.4 | Test analysis: NVDA | V+N | 5 min | Day 1 | Open browser → localhost:3000/analysis/NVDA → watch analysis stream |
| 4.5 | Verify Discord alert fires | V | 2 min | Day 1 | Manually POST to `/api/scanner/run` — check if Discord receives a message |
| 4.6 | Test LT score lookup | N | 3 min | Day 1 | localhost:3000/longterm → enter NVDA → should show LT score |
| 4.7 | Check Ollama sentiment working | V | 2 min | Day 1 | In the NVDA analysis, sentiment section should be non-empty |
| 4.8 | Check adversary agent fires | V | 2 min | Day 1 | Check logs: should see "Adversary: PASS" or "CHALLENGE" for NVDA |

---

## Phase 5 — DNA Seeding (overnight job)
| # | Task | Who | Time | Day | Notes |
|---|------|-----|------|-----|-------|
| 5.1 | Trigger full universe DNA seed | V | 1 min | Day 1 evening | `curl -X POST http://localhost:8000/api/admin/seed-dna` — runs overnight (8-12 hrs) |
| 5.2 | Check seeding progress next morning | V | 2 min | Day 2 | `curl http://localhost:8000/api/admin/dna-status` → shows total/high_quality/fresh counts |
| 5.3 | Verify DNA panel shows in analysis page | V+N | 2 min | Day 2 | localhost:3000/analysis/NVDA → scroll down → "NVDA Behavioral DNA" panel should appear |

---

## Phase 6 — Paper Trading Setup
| # | Task | Who | Time | Day | Notes |
|---|------|-----|------|-----|-------|
| 6.1 | Set portfolio value in .env | V | 1 min | Day 2 | `PAPER_PORTFOLIO_VALUE=150000.0` (or your target) |
| 6.2 | Run first nightly scan | V | 2 min | Day 2 | `curl http://localhost:8000/api/scanner/run` → waits ~2 min |
| 6.3 | Review scan results | N | 10 min | Day 2 | `curl http://localhost:8000/api/scanner/results` → top setups |
| 6.4 | Import Robinhood portfolio CSV | N | 5 min | Day 2 | localhost:3000/longterm → "Import Robinhood CSV" button |
| 6.5 | Review LT scores for your holdings | N | 15 min | Day 2 | localhost:3000/longterm → Portfolio tab → review scores + sell triggers |
| 6.6 | Check correlation panel | N | 5 min | Day 2 | Portfolio tab → scroll down → Pairwise Correlation panel |
| 6.7 | Analyze 3-5 scanner results manually | N | 30 min | Day 3 | Go to /analysis/SYMBOL for top scan results, review order ticket |
| 6.8 | Let automated jobs run for 5 days | Auto | — | Days 3-7 | Watchlist refresh (every 30min), position monitor (every 15min), DNA nightly |
| 6.9 | Review first week Discord alerts | N | 15 min | Day 7 | Check what compound signals fired, what positions need attention |

---

## Phase 7 — Backtesting (Week 2)
| # | Task | Who | Time | Day | Notes |
|---|------|-----|------|-----|-------|
| 7.1 | Check DNA coverage quality | V | 5 min | Day 8 | `/api/admin/dna-status` → want >80% of stocks with quality_score ≥50 |
| 7.2 | Review DNA panel for top 10 stocks | N | 20 min | Day 8 | Check NVDA, AMD, MSFT, GOOGL, AAPL, AVGO — validate DNA makes intuitive sense |
| 7.3 | Run agent performance check | V | 5 min | Day 8 | `curl http://localhost:8000/api/admin/agent-performance` → check fallback rates |
| 7.4 | Check first meta-research proposal | V | 15 min | Day 8 | `cat docs/update_proposals/*.md` → review findings |
| 7.5 | (Future) Backtest with VectorBT | V | 2-4 hrs | Week 2 | Not built yet — will be added as separate feature. Needs 90 days of paper data first. |

---

## Phase 8 — Paper Trading Active Period (Weeks 2-8)
| # | Task | Who | Time | Cadence | Notes |
|---|------|-----|------|---------|-------|
| 8.1 | Morning scan review | N | 10 min | Daily (market days) | Check Discord + scanner results each morning |
| 8.2 | Analyze specific setups | N | 20 min | 3x/week | /analysis/SYMBOL for any Discord alerts that look interesting |
| 8.3 | Review open paper positions | N | 5 min | Daily | Position monitor auto-alerts; just confirm nothing needs manual action |
| 8.4 | Weekly performance review | N+V | 30 min | Weekly | What won, what lost, any patterns |
| 8.5 | Review meta-research proposal | V+N | 15 min | Weekly (Sunday) | Check docs/update_proposals/YYYY-MM-DD.md |
| 8.6 | Update Robinhood CSV | N | 5 min | Weekly | Re-export and re-import if holdings changed |
| 8.7 | Check compound signals page | N | 5 min | 3x/week | Any semis cascade, VIX spike, or hyperscaler signals fired? |

---

## Phase 9 — Live Trading (Month 2-3+)
*Only after 6+ weeks of paper trading shows consistent results.*

| # | Task | Who | Time | Day | Notes |
|---|------|-----|------|-----|-------|
| 9.1 | Upgrade Tradier to live account | N | 10 min | Week 6-8 | developer.tradier.com → upgrade plan ($10/month) → get live API token |
| 9.2 | Update .env with live Tradier token | V | 2 min | Week 6-8 | `TRADIER_API_KEY=live_token` and `TRADIER_BASE_URL=https://api.tradier.com/v1` |
| 9.3 | Start with 25% of planned capital | N | — | Week 8 | Don't go full size immediately. System needs live calibration. |
| 9.4 | First live trade — only high conviction | N | — | Week 8 | Conviction ≥ 75 + no adversary challenges + no sell triggers on underlying |
| 9.5 | Scale capital over 4-8 weeks | N | — | Weeks 8-16 | Add capital only when win rate ≥ 55% on live |

---

## Quick Reference: Daily Checks (once live)
*Replace `trading.yourdomain.com` with your actual Vercel URL.*

| Check | Where | Takes |
|-------|-------|-------|
| New scanner alerts | Discord (phone notification) | 30 sec |
| Position health | trading.yourdomain.com → Positions tab | 2 min |
| LT sell triggers | trading.yourdomain.com/longterm → Portfolio | 2 min |
| Compound signals | trading.yourdomain.com (alerts section) | 1 min |
| DNA panel for any new stock | trading.yourdomain.com/analysis/SYMBOL | 2 min |
| Backend health check | api.yourdomain.com/health | 5 sec |

---

## Troubleshooting Reference
| Symptom | Likely cause | Fix |
|---------|-------------|-----|
| `torch.cuda.is_available()` = False | PyTorch/CUDA version mismatch | Reinstall torch with exact CUDA version (see cheat sheet) |
| FAISS import error or CPU mode | pip installed CPU version | Use conda: `conda install -c pytorch -c nvidia faiss-gpu` |
| `psycopg2.OperationalError` | DB not running or wrong URL | `sudo systemctl start postgresql` |
| Ollama returns empty | Model not pulled or service not started | `ollama serve` in separate terminal; `ollama pull llama3.1:8b` |
| FMP returns empty arrays | Wrong API key or plan too low | Check `settings.FMP_API_KEY` + verify Starter plan at FMP dashboard |
| DNA panel blank in UI | DNA not seeded for that stock | POST /api/admin/seed-dna or wait for nightly batch |
| Adversary always returns PASS | deepseek-r1:7b not pulled | `ollama pull deepseek-r1:7b` |
| High fallback rates in agent monitor | Anthropic API key low credit | Top up at console.anthropic.com |
| `pandas-ta` import errors | Version mismatch | `pip install pandas-ta==0.3.14b0` |
| frontend blank / API errors | Wrong NEXT_PUBLIC_API_URL | On Vercel: Settings → Env Vars → set `NEXT_PUBLIC_API_URL=https://api.yourdomain.com/api` |
| Vercel build fails | Wrong root directory | Vercel project settings → Root Directory → set to `frontend` |
| Cloudflare tunnel offline | cloudflared service crashed | `sudo systemctl restart cloudflared && sudo systemctl status cloudflared` |
| `api.yourdomain.com` unreachable | Backend not running on PC | `curl localhost:8000/health` on PC — if that works, the tunnel config is wrong |
| CORS errors from Vercel | Origin not in allow list | Add Vercel URL to `CORS_ORIGINS` in `.env` and restart backend |

---

## Model Assignment Reference
| Agent | Model | Why |
|-------|-------|-----|
| Fundamental analyst | claude-sonnet-4-6 | Structured data → narrative, cheap |
| Technical analyst | claude-sonnet-4-6 | Pattern naming, cheap |
| Volatility analyst | claude-sonnet-4-6 | IV narrative, cheap |
| Sentiment analyst | llama3.1:8b (Ollama) | Free local, good enough for filtering |
| **Trader agent** | **claude-opus-4-7** | Synthesizes all 4 reports + DNA + LT + memory → conviction score. Only decision where Opus matters. |
| Risk manager | claude-sonnet-4-6 | Checklist task, not synthesis |
| **Adversary agent** | **deepseek-r1:7b (Ollama)** | Reasoning model, free local, challenges trader thesis |
| Postmortem / lesson | claude-sonnet-4-6 | Short lesson writing |
| Ollama news filter | llama3.1:8b (Ollama) | Free, kills 90% noise |
| Meta-researcher | llama3.1:8b (Ollama) | Paper summarization, trade IC analysis |
| Embeddings (RAG) | nomic-embed-text (Ollama) | Free local embeddings |

---

## Phase 10 — Remote Access + Deployment (So N Can Check From Anywhere)

**Architecture:**
- **Frontend → Vercel** (free, CDN, N accesses from phone/laptop anywhere)
- **Backend → Cloudflare Tunnel** (free, exposes PC to internet, stable URL even with dynamic IP)
- **PC stays as compute host** — Ollama GPU models, Postgres, Redis, APScheduler all run locally

> ⚠️ The site is only accessible when the PC is on. For a market-hours trading tool this is fine — just leave the PC on during the trading day. If you want 24/7 uptime, see the "Always-On Upgrade" note at the bottom.

### Step 1 — Cloudflare Tunnel (backend, ~20 min)
| # | Task | Who | Time | Command / Notes |
|---|------|-----|------|-----------------|
| 10.1 | Sign up for a free Cloudflare account | V | 3 min | cloudflare.com — just needs an email |
| 10.2 | Add a domain to Cloudflare OR use free tunnel URL | V | 5 min | Option A: buy a cheap domain (~$10/yr at Cloudflare, e.g. `yourname-trading.com`) → add to Cloudflare. Option B: skip domain for now and use the free `*.cfargotunnel.com` subdomain |
| 10.3 | Install cloudflared on PC | V | 2 min | `curl -L https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64.deb -o cloudflared.deb && sudo dpkg -i cloudflared.deb` |
| 10.4 | Authenticate cloudflared | V | 2 min | `cloudflared tunnel login` → opens browser, approve |
| 10.5 | Create named tunnel | V | 1 min | `cloudflared tunnel create trading-api` → note the tunnel ID shown |
| 10.6 | Configure tunnel → your PC's backend | V | 5 min | Create `~/.cloudflared/config.yml` (see config below) |
| 10.7 | Route DNS to tunnel (if you have a domain) | V | 1 min | `cloudflared tunnel route dns trading-api api.yourdomain.com` |
| 10.8 | Start tunnel as a system service | V | 3 min | `sudo cloudflared service install && sudo systemctl start cloudflared` |
| 10.9 | Verify backend accessible from phone | V+N | 2 min | Open `https://api.yourdomain.com/health` on phone → should see `{"status":"ok"}` |

**~/.cloudflared/config.yml:**
```yaml
tunnel: trading-api          # your tunnel name from step 10.5
credentials-file: /home/YOUR_USER/.cloudflared/<tunnel-id>.json

ingress:
  - hostname: api.yourdomain.com   # your domain (or remove this line for free URL)
    service: http://localhost:8000
  - service: http_status:404
```

**Free URL (no domain):** If you skipped the domain, run `cloudflared tunnel run trading-api` and it prints a URL like `https://abc123xyz.cfargotunnel.com`. Use that as your backend URL everywhere. Not memorable but free and permanent.

---

### Step 2 — Vercel Frontend (~15 min)
| # | Task | Who | Time | Notes |
|---|------|-----|------|-------|
| 10.10 | Push project to GitHub (if not already) | V | 5 min | `git init && git remote add origin <your-github-repo> && git push -u origin main` |
| 10.11 | Sign up for Vercel | V | 2 min | vercel.com → "Continue with GitHub" — it's free |
| 10.12 | Import project | V | 3 min | Vercel dashboard → "Add New Project" → import your GitHub repo → set **Root Directory** to `frontend` |
| 10.13 | Set environment variable | V | 2 min | In Vercel project → Settings → Environment Variables → add: `NEXT_PUBLIC_API_URL` = `https://api.yourdomain.com/api` (your Cloudflare URL + `/api`) |
| 10.14 | Deploy | V | 3 min | Vercel auto-builds on first connect. Watch build logs — should complete in ~2 min. |
| 10.15 | Add custom domain (optional) | V | 5 min | Vercel → Settings → Domains → add `trading.yourdomain.com` → Cloudflare DNS: CNAME `trading` → `cname.vercel-dns.com` |
| 10.16 | Update CORS in backend .env | V | 1 min | `CORS_ORIGINS=["https://trading.yourdomain.com","https://yourapp.vercel.app"]` then restart backend |
| 10.17 | Test full flow from phone | N | 5 min | Open the Vercel URL on phone → go to /analysis/NVDA → should load and show live data from your PC |

**Future deploys:** Every `git push` to `main` triggers an automatic Vercel redeploy. Backend changes just restart uvicorn on the PC — no redeploy needed.

---

### Always-On Upgrade (Optional, ~$5/month)
*Only needed if you want the site accessible when the PC is off.*

Run the backend on a tiny VPS instead of the PC. You lose GPU (Ollama switches to CPU or Groq API), but the site stays up 24/7:

| Provider | Cost | What you get |
|----------|------|-------------|
| Hetzner CX22 | €3.29/month | 2 vCPU, 4GB RAM, 40GB SSD — plenty for FastAPI + Postgres + Redis |
| Railway | $5/month | Managed, auto-deploys from git, built-in Postgres |
| Render | Free → $7/month | Free tier sleeps after 15 min; paid stays awake |

**Ollama without GPU:** Replace `OLLAMA_CHAT_MODEL` calls with Groq API (free 14,400 requests/day, llama3.1-8b). Adversary agent: use Deepseek API (~$0.14/M tokens). The PC still runs DNA seeding nightly via a cron job to the cloud server. This is the Phase 9 upgrade path once you go live.

---

## Weekly Automated Jobs (all managed by APScheduler)
| Job | Schedule | What it does |
|-----|----------|-------------|
| Nightly scan | 6 PM ET Mon-Fri | Scanner: 5K stocks → top 10 setups |
| DNA batch | 7 PM ET Mon-Fri | Refresh DNA for watchlist + stale stocks |
| Watchlist refresh | Every 30 min, 9 AM-4 PM | Keep watchlist scores current |
| Position monitor | Every 15 min, 9 AM-4 PM | Check stop/target on all open positions |
| Catalyst detector | Every 30 min, 9 AM-4 PM | Compound signal checks |
| Weekly compaction | Sunday 8 PM ET | Compact agent memory, flush monitor to DB |
| Meta-research | Sunday 9 PM ET | Trade IC analysis + arXiv scan + proposal |
