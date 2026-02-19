# EBAP — Makefile
# Unified task runner for the Enterprise Behavioral Analytics Platform.
# Usage: make <target>

.DEFAULT_GOAL := help
.PHONY: help build up down logs restart \
        submit-stream stop-stream \
        test-unit test-integration test-e2e lint format \
        health clean seed-data generate-data

# ---------------------------------------------------------------------------
# Docker image
# ---------------------------------------------------------------------------

build:  ## Build the custom Spark Docker image
	docker build -t custom-spark:latest -f infrastructure/docker/spark/Dockerfile .

# ---------------------------------------------------------------------------
# Stack lifecycle
# ---------------------------------------------------------------------------

up:  ## Start all long-running services (detached)
	docker compose up -d kafka kafka-2 postgres debezium-connect redis minio \
	    spark-master-streaming spark-worker

down:  ## Stop all services and remove volumes
	docker compose down -v

restart:  ## Restart all services
	docker compose down -v && $(MAKE) up

logs:  ## Tail logs for all running services
	docker compose logs -f

# ---------------------------------------------------------------------------
# Init containers (one-shot setup)
# ---------------------------------------------------------------------------

init-kafka:  ## Create Kafka topics
	docker compose run --rm kafka-init

init-debezium:  ## Register the Debezium CDC connector
	docker compose run --rm debezium-init

init-minio:  ## Create MinIO lakehouse buckets
	docker compose run --rm minio-init

init-all: init-minio init-kafka init-debezium  ## Run all init containers in order

# ---------------------------------------------------------------------------
# Spark streaming job
# ---------------------------------------------------------------------------

submit-stream:  ## Submit the PySpark structured streaming job
	docker compose up --no-deps spark-streaming-submit

stop-stream:  ## Stop the streaming submit container
	docker compose stop spark-streaming-submit

# ---------------------------------------------------------------------------
# Testing
# ---------------------------------------------------------------------------

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

health:  ## Check health of all running services
	python scripts/health_check.py

seed-data:  ## Seed PostgreSQL with sample user data
	docker exec ebap-postgres psql -U admin -d ebap_db -f /docker-entrypoint-initdb.d/01-seed-postgres.sql

generate-data:  ## Produce synthetic events to Kafka
	python scripts/generate_test_data.py

kpi:  ## Check real-time KPIs from Redis
	docker exec ebap-redis redis-cli GET kpi:total_revenue
	docker exec ebap-redis redis-cli GET kpi:active_users

# ---------------------------------------------------------------------------
# Cleanup
# ---------------------------------------------------------------------------

clean:  ## Remove containers, volumes, and locally built images
	docker compose down -v --rmi local

# ---------------------------------------------------------------------------
# Help
# ---------------------------------------------------------------------------

help:  ## Show this help message
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | \
	    awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-20s\033[0m %s\n", $$1, $$2}'
