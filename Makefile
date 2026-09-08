COMPOSE = docker compose --env-file .env -f ops/compose/compose.yml
.PHONY: configure up down infra logs test check migrate contracts backup
configure:
	python3 ops/configure.py
up:
	$(COMPOSE) up -d --build
down:
	$(COMPOSE) down
infra:
	$(COMPOSE) up -d postgres redis opensearch minio
logs:
	$(COMPOSE) logs -f --tail=100
migrate:
	cd apps/backend && uv run --env-file ../../.env alembic upgrade head
test:
	cd apps/backend && uv run pytest -q ../../tests
check:
	cd apps/backend && uv run ruff check src ../../tests && uv run ruff format --check src ../../tests
	cd apps/web && npm run typecheck && npm run build
contracts:
	cd apps/backend && uv run python ../../ops/export_contracts.py
	cd apps/web && npx openapi-typescript ../../packages/contracts/openapi.json -o ../../packages/contracts/api.d.ts
backup:
	bash ops/backup.sh
