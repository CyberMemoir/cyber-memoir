COMPOSE = docker compose --env-file .env -f ops/compose/compose.yml
EVAL_CHECK = ../../evals/run.py ../../evals/checkpoint.py ../../evals/build_gold.py ../../evals/score_buckets.py ../../evals/load_curation.py ../../evals/model_assets.py ../../evals/model_probe.py
DEMO_CHECK = ../../ops/demo.py ../../ops/demo_server.py ../../ops/demo_fixtures.py
E2E_CHECK = ../../ops/e2e_server.py
REVISION_CHECK = migrations/versions/f5a6b7c8d9e0_review_edit_versions.py
.PHONY: configure up down infra logs test check migrate contracts backup demo
configure:
	python3 ops/configure.py
up:
	$(COMPOSE) up -d --build
down:
	$(COMPOSE) down
infra:
	$(COMPOSE) up -d --build postgres redis opensearch minio
logs:
	$(COMPOSE) logs -f --tail=100
migrate:
	cd apps/backend && uv run --env-file ../../.env alembic upgrade head
test:
	cd apps/backend && uv run pytest -q ../../tests
check:
	cd apps/backend && uv run ruff check src ../../tests $(EVAL_CHECK) $(DEMO_CHECK) $(E2E_CHECK) $(REVISION_CHECK) && uv run ruff format --check src ../../tests $(EVAL_CHECK) $(DEMO_CHECK) $(E2E_CHECK) $(REVISION_CHECK)
	cd apps/web && npm run typecheck && npm run build
contracts:
	cd apps/backend && uv run python ../../ops/export_contracts.py
	cd apps/web && npx openapi-typescript ../../packages/contracts/openapi.json -o ../../packages/contracts/api.d.ts
backup:
	bash ops/backup.sh
demo:
	cd apps/backend && uv run --project . python ../../ops/demo.py
