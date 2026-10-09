SHELL := /bin/bash
UV ?= uv
API := apps/api

.DEFAULT_GOAL := help

.PHONY: help
help: ## Show this help
	@grep -hE '^[a-zA-Z_-]+:.*?## ' $(MAKEFILE_LIST) | awk 'BEGIN{FS=":.*?## "}{printf "  \033[36m%-16s\033[0m %s\n", $$1, $$2}'

.PHONY: setup
setup: ## Install all dependencies (Python + Node) and create .env
	@test -f .env || (cp .env.example .env && echo "created .env from .env.example")
	cd $(API) && $(UV) sync --extra ai
	pnpm install

.PHONY: up
up: ## Start backing services + api + worker + beat (web runs on host)
	docker compose up -d --build
	@echo "api      http://localhost:8000/docs"
	@echo "mailpit  http://localhost:8025"
	@echo "now run: make dev-web"

.PHONY: up-full
up-full: ## Start everything including web in a container
	docker compose --profile full up -d --build

.PHONY: up-native
up-native: ## Start backing services WITHOUT Docker (Homebrew postgres/redis + local chroma/mjml)
	./scripts/native-up.sh

.PHONY: down-native
down-native: ## Stop the natively-run chroma + mjml processes
	./scripts/native-down.sh

.PHONY: down
down: ## Stop all services (keeps volumes)
	docker compose down

.PHONY: nuke
nuke: ## Stop all services and DELETE all local data volumes
	docker compose down -v

.PHONY: logs
logs: ## Tail logs for all services
	docker compose logs -f --tail=100

.PHONY: ps
ps: ## Show service status
	docker compose ps

.PHONY: dev-api
dev-api: ## Run the API on the host (needs backing services up)
	cd $(API) && $(UV) run uvicorn sendox_api.main:app --reload --port 8000

.PHONY: dev-worker
dev-worker: ## Run a Celery worker on the host (threads pool — see DEV-ENVIRONMENT.md)
	cd $(API) && $(UV) run celery -A sendox_api.worker.celery_app worker \
		--loglevel=INFO --pool=threads --concurrency=4

.PHONY: dev-web
dev-web: ## Run the Next.js dev server on the host
	pnpm dev:web

.PHONY: test
test: test-api test-web ## Run all tests

.PHONY: test-api
test-api: ## Run Python tests
	cd $(API) && $(UV) run pytest -q

.PHONY: test-web
test-web: ## Build the web app (stands in for tests until 0.3)
	pnpm build:web

.PHONY: lint
lint: ## Lint and type-check everything
	cd $(API) && $(UV) run ruff check . && $(UV) run ruff format --check . && $(UV) run mypy src
	pnpm lint:web

.PHONY: fmt
fmt: ## Auto-format everything
	cd $(API) && $(UV) run ruff format . && $(UV) run ruff check --fix .

.PHONY: migrate
migrate: ## Apply database migrations
	cd $(API) && $(UV) run alembic upgrade head

.PHONY: migration
migration: ## Autogenerate a migration: make migration m="add contacts"
	cd $(API) && $(UV) run alembic revision --autogenerate -m "$(m)"

.PHONY: db-reset
db-reset: ## Drop and recreate the schema (DESTROYS local data)
	cd $(API) && $(UV) run alembic downgrade base && $(UV) run alembic upgrade head

.PHONY: status-page
status-page: ## Regenerate docs/status-page.html from live API data (then publish it)
	$(UV) run --quiet python scripts/status-page.py

.PHONY: devlog
devlog: ## Regenerate docs/Sendox-Development-Log.docx from docs/DEVLOG.md
	$(UV) run --quiet --with python-docx python scripts/devlog-docx.py

.PHONY: verify
verify: ## End-to-end localhost check of everything phase 0.1 delivers
	./scripts/verify.sh

.PHONY: health
health: ## Print the API readiness report
	@curl -s http://localhost:8000/health/ready | python3 -m json.tool
