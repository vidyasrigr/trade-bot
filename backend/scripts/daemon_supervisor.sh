#!/usr/bin/env bash
# Daemon supervisor (0620.3 Phase S) — host-equivalent of systemd/supervisord.
# Keeps the FMP + chain-bank daemons alive: if a daemon's python process is gone,
# it relaunches it. Detached via setsid so it survives shell/process-group cleanup
# (the failure mode that killed daemons between sessions).
#
# Usage:
#   setsid bash scripts/daemon_supervisor.sh >> data/cache/_supervisor.log 2>&1 < /dev/null &
#   (or: scripts/daemon_supervisor.sh once   # single check, for testing)
set -u

BACKEND="$(cd "$(dirname "$0")/.." && pwd)"
PY="$BACKEND/../venv/bin/python"
cd "$BACKEND" || exit 1

LOG_FMP="$BACKEND/data/cache/fmp/_daemon_stdout.log"
LOG_CHAIN="$BACKEND/data/marketdata_cache/_bank_stdout.log"
SUP_LOG="$BACKEND/data/cache/_supervisor.log"

ts() { date '+%Y-%m-%d %H:%M:%S'; }

running() {  # $1 = module path fragment
  pgrep -f "[p]ython -m $1" >/dev/null 2>&1
}

start_fmp() {
  setsid "$PY" -m scripts.fmp_daemon >> "$LOG_FMP" 2>&1 < /dev/null &
  echo "[$(ts)] supervisor: (re)started fmp_daemon" | tee -a "$SUP_LOG"
}

start_chain() {
  setsid "$PY" -m scripts.chain_bank_daemon >> "$LOG_CHAIN" 2>&1 < /dev/null &
  echo "[$(ts)] supervisor: (re)started chain_bank_daemon" | tee -a "$SUP_LOG"
}

check_once() {
  running "scripts.fmp_daemon"        || start_fmp
  running "scripts.chain_bank_daemon" || start_chain
}

if [ "${1:-}" = "once" ]; then
  check_once
  exit 0
fi

# singleton guard: only one supervisor loop may run (avoids duplicate restarts/races)
exec 9>"$BACKEND/data/cache/.supervisor.lock"
if ! flock -n 9; then
  echo "[$(ts)] supervisor: another instance holds the lock, exiting" >> "$SUP_LOG"
  exit 0
fi

echo "[$(ts)] supervisor: loop start (interval 60s, pid $$)" | tee -a "$SUP_LOG"
while true; do
  check_once
  sleep 60
done
