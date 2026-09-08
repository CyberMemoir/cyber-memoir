#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
test "$#" -eq 1 || { echo 'Usage: bash ops/restore.sh /absolute/backup/directory'; exit 1; }
backup="$(cd "$1" && pwd)"
test -s "$backup/postgres.dump"
test -f "$backup/manifest.json"
compose=(docker compose --env-file .env -f ops/compose/compose.yml)
tables=$("${compose[@]}" exec -T postgres psql -U memoir -d memoir -At -c "SELECT count(*) FROM pg_tables WHERE schemaname='public'")
test "$tables" = "0" || { echo 'Restore requires an empty PostgreSQL public schema. No existing data was changed.'; exit 1; }
"${compose[@]}" run --rm --no-deps -T -v "$backup:/backup:ro" api python -m cyber_memoir.adapters.backup verify /backup
"${compose[@]}" stop -t 120 api worker
"${compose[@]}" run --rm --no-deps -T -v "$backup:/backup:ro" api python -m cyber_memoir.adapters.backup restore /backup
"${compose[@]}" exec -T postgres pg_restore -U memoir -d memoir --no-owner --exit-on-error < "$backup/postgres.dump"
echo 'Restored. Run make up, then rebuild search indexes from the review workbench.'
