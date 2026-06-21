# Daemon supervision (0620.3 Phase S)

Two long-running daemons must stay alive: the FMP ingest daemon and the MarketData
chain-bank daemon. They died a few times between sessions on process-group cleanup.

## Active in this environment
`scripts/daemon_supervisor.sh` — a flock-guarded watchdog loop: every 60s it checks each
daemon and relaunches any that died (`setsid`-detached), logging to
`data/cache/_supervisor.log`. Single-instance via `data/cache/.supervisor.lock`.

Run (host-equivalent of a service manager):
```
setsid bash scripts/daemon_supervisor.sh >> data/cache/_supervisor.log 2>&1 < /dev/null &
# one-shot restart of any dead daemon:
bash scripts/daemon_supervisor.sh once
```

## Production answer (systemd --user) — the real fix
On a host with systemd user-lingering enabled (`loginctl enable-linger $USER`), install the
units below to `~/.config/systemd/user/` and `systemctl --user enable --now tradebot-*.service`.
Restart=always gives true cross-session auto-restart (no watchdog needed).

`tradebot-fmp.service`:
```
[Unit]
Description=TradeBot FMP ingest daemon
After=network-online.target

[Service]
WorkingDirectory=%h/Projects/Trade Bot/backend
ExecStart=%h/Projects/Trade Bot/venv/bin/python -m scripts.fmp_daemon
Restart=always
RestartSec=10

[Install]
WantedBy=default.target
```

`tradebot-chainbank.service`:
```
[Unit]
Description=TradeBot MarketData chain-bank daemon
After=network-online.target

[Service]
WorkingDirectory=%h/Projects/Trade Bot/backend
ExecStart=%h/Projects/Trade Bot/venv/bin/python -m scripts.chain_bank_daemon
Restart=always
RestartSec=30

[Install]
WantedBy=default.target
```
