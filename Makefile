.PHONY: help install dev test test-unit test-integration test-security lint format typecheck migrate db-up db-down clean run worker beat flower

help:
	@echo "Gabster AI Development & Operations CLI"
	@echo "========================================="
	@echo "install          : Install production dependencies"
	@echo "dev              : Install development dependencies"
	@echo "run              : Start API server in dev mode"
	@echo "worker           : Start Celery worker"
	@echo "beat             : Start Celery beat scheduler"
	@echo "flower           : Start Celery flower monitoring"
	@echo "db-up            : Start PostgreSQL and Redis via Docker Compose"
	@echo "db-down          : Stop PostgreSQL and Redis containers"
	@echo "migrate          : Apply all database migrations"
	@echo "migrate-create   : Generate new migration (msg='...')"
	@echo "migrate-down     : Revert last migration"
	@echo "seed             : Populate baseline system data (plans, models, roles)"
	@echo "lint             : Run ruff linter"
	@echo "format           : Auto-format code with black and ruff"
	@echo "typecheck        : Run strict static analysis with mypy"
	@echo "test             : Run full test suite with coverage report"
	@echo "test-unit        : Run unit tests"
	@echo "test-integration : Run integration tests"
	@echo "test-security    : Run tenant isolation & security tests"
	@echo "clean            : Remove temporary and cache files"

install:
	poetry install --only main

dev:
	poetry install

run:
	poetry run uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload

worker:
	poetry run celery -A app.workers.celery_app worker --loglevel=INFO -Q default,ai,ingestion,webhooks,campaigns -c 4

beat:
	poetry run celery -A app.workers.celery_app beat --loglevel=INFO

flower:
	poetry run celery -A app.workers.celery_app flower --port=5555

db-up:
	docker compose -f docker/docker-compose.dev.yml up -d postgres redis

db-down:
	docker compose -f docker/docker-compose.dev.yml down

migrate:
	poetry run alembic upgrade head

migrate-create:
	@test -n "$(msg)" || (echo "msg is required, e.g. make migrate-create msg='add_new_table'" && exit 1)
	poetry run alembic revision --autogenerate -m "$(msg)"

migrate-down:
	poetry run alembic downgrade -1

seed:
	poetry run python scripts/seed_system_data.py

lint:
	poetry run ruff check app tests

format:
	poetry run ruff check --fix app tests
	poetry run black app tests

typecheck:
	poetry run mypy app

test:
	poetry run pytest tests/

test-unit:
	poetry run pytest tests/unit/

test-integration:
	poetry run pytest tests/integration/

test-security:
	poetry run pytest tests/security/

clean:
	find . -type d -name "__pycache__" -exec rm -rf {} +
	find . -type d -name ".pytest_cache" -exec rm -rf {} +
	find . -type d -name ".mypy_cache" -exec rm -rf {} +
	find . -type d -name ".ruff_cache" -exec rm -rf {} +
	rm -rf .coverage htmlcov/
