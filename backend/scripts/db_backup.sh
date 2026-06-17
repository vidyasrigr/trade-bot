#!/usr/bin/env bash
# Daily Postgres backup — pg_dump to data/backups/, keep last 14 days.
#
# Usage:
#   ./scripts/db_backup.sh                  # uses DATABASE_URL from env
#
# Crontab entry (run at 11:50 PM ET nightly):
#   50 23 * * * cd /Users/V/Projects/Options/backend && \
#               ./scripts/db_backup.sh >> data/backups/backup.log 2>&1
#
# Or via launchd on macOS — see misc/launchd_backup.plist if present.

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BACKUP_DIR="${REPO_ROOT}/data/backups"
RETAIN_DAYS=14

mkdir -p "${BACKUP_DIR}"

if [[ -z "${DATABASE_URL:-}" ]]; then
    if [[ -f "${REPO_ROOT}/.env" ]]; then
        # shellcheck disable=SC1091
        set -a; source "${REPO_ROOT}/.env"; set +a
    fi
fi

if [[ -z "${DATABASE_URL:-}" ]]; then
    echo "[$(date)] FATAL: DATABASE_URL not set" >&2
    exit 1
fi

TIMESTAMP=$(date +%Y%m%d_%H%M%S)
DUMP_FILE="${BACKUP_DIR}/options_${TIMESTAMP}.sql.gz"

echo "[$(date)] Starting backup → ${DUMP_FILE}"
pg_dump "${DATABASE_URL}" \
    --no-owner --no-acl --clean --if-exists \
    | gzip -9 > "${DUMP_FILE}"

SIZE=$(du -h "${DUMP_FILE}" | cut -f1)
echo "[$(date)] Backup complete: ${SIZE}"

# Prune old backups
echo "[$(date)] Pruning backups older than ${RETAIN_DAYS} days"
find "${BACKUP_DIR}" -name "options_*.sql.gz" -type f -mtime "+${RETAIN_DAYS}" -delete

# Quick health log
REMAINING=$(find "${BACKUP_DIR}" -name "options_*.sql.gz" -type f | wc -l | xargs)
echo "[$(date)] ${REMAINING} backups retained in ${BACKUP_DIR}"
