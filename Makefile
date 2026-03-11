# Nexus — Makefile
# Unified task runner for the Nexus real-time pipeline.
# Usage: make <target>

.DEFAULT_GOAL := help
.PHONY: help build up up-infra up-cdc up-spark up-api down logs restart \
        test-unit test-integration test-e2e lint format \
        health clean generate-data generate generate-kafka generate-postgres generate-stress generate-light \
        logs-transactions logs-infrastructure logs-derived logs-api redis-cli redis-monitor

# ---------------------------------------------------------------------------
# Generator variables (override on the command line, e.g. make generate RATE=50)
# ---------------------------------------------------------------------------
RATE     ?= 20
DURATION ?= 300
PRESET   ?= demo
ERROR_RATE ?= 0.05

# ---------------------------------------------------------------------------
# Docker image
# ---------------------------------------------------------------------------

build:  ## Build the custom Spark image
	docker build -t custom-spark:latest -f infrastructure/docker/spark/Dockerfile .

# ---------------------------------------------------------------------------
# Stack lifecycle
# ---------------------------------------------------------------------------

up:  ## Start the full Nexus stack
	docker compose up -d

up-infra:  ## Start Kafka, schema registry, Postgres, and Redis
	docker compose up -d kafka-1 kafka-2 schema-registry postgres redis

up-cdc:  ## Start Debezium services
	docker compose up -d debezium-connect debezium-init

up-spark:  ## Start Spark master, worker, and jobs
	docker compose up -d spark-master spark-worker spark-job-transactions spark-job-infrastructure spark-job-derived

up-api:  ## Start FastAPI backend
	docker compose up -d nexus-api

down:  ## Stop all services and remove volumes
	docker compose down -v --remove-orphans

restart:  ## Restart the full stack
	docker compose down -v && $(MAKE) up

logs:  ## Tail logs for all running services
	docker compose logs -f

test-unit:  ## Run unit tests (no services required)
	pytest tests/unit/ -v

test-integration:  ## Run integration tests (services must be running)
	pytest tests/integration/ -v

test-e2e:  ## Run end-to-end tests (full stack must be running)
	pytest tests/e2e/ -v

test-all:  ## Run all tests
	pytest tests/ -v

# ---------------------------------------------------------------------------
# Code quality
# ---------------------------------------------------------------------------

lint:  ## Run ruff linter across src/ and tests/
	ruff check src/ tests/

format:  ## Auto-format src/ and tests/ with ruff
	ruff format src/ tests/

# ---------------------------------------------------------------------------
# Operational utilities
# ---------------------------------------------------------------------------

health:  ## Check health of Nexus services
	python scripts/health_check.py

generate-data:  ## Generate Nexus CDC + Kafka test traffic (legacy alias)
	python scripts/generate_test_data.py --mode all --rate $(RATE) --duration $(DURATION) --error-rate $(ERROR_RATE)

generate:  ## Generate CDC + Kafka traffic (mode=all). Supports RATE=, DURATION=, PRESET=, ERROR_RATE=
	python scripts/generate_test_data.py --mode all --rate $(RATE) --duration $(DURATION) --preset $(PRESET) --error-rate $(ERROR_RATE)

generate-kafka:  ## Generate Kafka-only traffic. Supports RATE=, DURATION=, PRESET=, ERROR_RATE=
	python scripts/generate_test_data.py --mode kafka --rate $(RATE) --duration $(DURATION) --preset $(PRESET) --error-rate $(ERROR_RATE)

generate-postgres:  ## Generate PostgreSQL/CDC-only traffic. Supports RATE=, DURATION=, PRESET=, ERROR_RATE=
	python scripts/generate_test_data.py --mode postgres --rate $(RATE) --duration $(DURATION) --preset $(PRESET) --error-rate $(ERROR_RATE)

generate-stress:  ## Stress test at 200 req/s for 3 minutes
	python scripts/generate_test_data.py --mode all --preset extreme --rate 200 --duration 180 --size large

generate-light:  ## Light traffic for quick smoke tests (5 req/s, 2 min)
	python scripts/generate_test_data.py --mode all --preset light

logs-transactions:  ## Tail transaction job logs
	docker compose logs -f spark-job-transactions

logs-infrastructure:  ## Tail infrastructure job logs
	docker compose logs -f spark-job-infrastructure

logs-derived:  ## Tail derived job logs
	docker compose logs -f spark-job-derived

logs-api:  ## Tail API logs
	docker compose logs -f nexus-api

redis-cli:  ## Open a Redis shell
	docker compose exec redis redis-cli

redis-monitor:  ## Watch Redis commands in real time
	docker compose exec redis redis-cli MONITOR

# ---------------------------------------------------------------------------
# Cleanup
# ---------------------------------------------------------------------------

clean:  ## Remove containers, volumes, and checkpoints
	docker compose down -v --remove-orphans
	rm -rf /tmp/nexus-checkpoints

# ---------------------------------------------------------------------------
# Help
# ---------------------------------------------------------------------------

help:  ## Show this help message
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | \
	    awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-20s\033[0m %s\n", $$1, $$2}'
