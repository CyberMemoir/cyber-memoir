#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
compose=(docker compose --env-file .env -f ops/compose/compose.yml)
destination="$(pwd)/.data/backups/$(date -u +%Y%m%dT%H%M%SZ)"
mkdir -p "$destination"
chmod 700 "$destination"
running=()
while IFS= read -r service; do
  case "$service" in api|worker) running+=("$service");; esac
done < <("${compose[@]}" ps --status running --services)
resume() { if ((${#running[@]})); then "${compose[@]}" start "${running[@]}" >/dev/null; fi; }
trap resume EXIT
if ((${#running[@]})); then "${compose[@]}" stop -t 120 "${running[@]}"; fi
"${compose[@]}" exec -T postgres pg_dump -U memoir -d memoir -Fc > "$destination/postgres.dump"
"${compose[@]}" run --rm --no-deps -T --user "$(id -u):$(id -g)" -v "$destination:/backup" api \
  python -m cyber_memoir.adapters.backup export /backup
printf 'Backup completed: %s\n' "$destination"
