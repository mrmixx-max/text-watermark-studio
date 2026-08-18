.PHONY: help venv install dev test test-cov lint format type-check security clean build docker-build docker-run docker-prod release-check

PYTHON ?= python
VENV ?= .venv
ifeq ($(OS),Windows_NT)
VENV_BIN := $(VENV)/Scripts
else
VENV_BIN := $(VENV)/bin
endif
PIP := $(VENV_BIN)/pip
PYTEST := $(VENV_BIN)/pytest
UVICORN := $(VENV_BIN)/uvicorn
RUFF := $(VENV_BIN)/ruff

help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-20s\033[0m %s\n", $$1, $$2}'

venv: ## Create virtual environment
	$(PYTHON) -m venv $(VENV)

install: venv ## Install production dependencies
	$(PIP) install --upgrade pip
	$(PIP) install -e .

dev: venv ## Install development dependencies
	$(PIP) install --upgrade pip
	$(PIP) install -e .[dev,tui,bpe]

test: ## Run tests
	$(PYTEST) -q

test-cov: ## Run tests with coverage
	$(PYTEST) -q --cov=ai_watermark_toolkit --cov-report=term-missing --cov-report=html --cov-report=xml

test-ci: ## Run tests for CI (with junit output)
	$(PYTEST) -q --cov=ai_watermark_toolkit --cov-report=xml --junitxml=test-results.xml

lint: ## Run linter
	$(RUFF) check src/ tests/

lint-fix: ## Fix lint issues
	$(RUFF) check --fix src/ tests/

format: ## Format code
	$(RUFF) format src/ tests/

format-check: ## Check formatting
	$(RUFF) format --check src/ tests/

security: ## Run security scans
	$(VENV_BIN)/bandit -r src/ -c pyproject.toml
	$(VENV_BIN)/ruff check src/ tests/ --select S

type-check: ## Run type checker (requires mypy in dev deps)
	$(VENV_BIN)/mypy src/ || true

run: ## Run CLI serve
	$(VENV_BIN)/ai-wm serve --host 127.0.0.1 --port 8080

api: ## Run API server with reload
	$(UVICORN) ai_watermark_toolkit.api.fastapi_app:app --host 127.0.0.1 --port 8080 --reload

worker: ## Run streams worker
	$(VENV_BIN)/python -m ai_watermark_toolkit.workers.streams_worker

build: ## Build Python package
	$(VENV_BIN)/python -m build

docker-build: ## Build Docker image
	docker build -t text-watermark-studio:latest .

docker-run: ## Run Docker Compose (development)
	docker-compose up -d

docker-prod: ## Run Docker Compose (production)
	docker-compose -f docker-compose.yml -f docker-compose.prod.yml up -d

docker-stop: ## Stop Docker Compose
	docker-compose down

docker-logs: ## View Docker logs
	docker-compose logs -f

docker-test: docker-build ## Test Docker image
	docker run --rm text-watermark-studio:latest python -c "import ai_watermark_toolkit; print('Docker image OK')"

release-check: ## Check release readiness
	@echo "=== Release Checks ==="
	@echo "1. Running tests..."
	$(MAKE) test
	@echo "2. Running linter..."
	$(MAKE) lint
	@echo "3. Running security scan..."
	$(MAKE) security
	@echo "4. Building package..."
	$(MAKE) build
	@echo "5. Checking package..."
	$(VENV_BIN)/twine check dist/*
	@echo "=== All checks passed ==="

clean: ## Clean build artifacts
	rm -rf .venv build dist *.egg-info .pytest_cache .mypy_cache .ruff_cache
	rm -rf htmlcov .coverage coverage.xml test-results.xml bandit-results.json
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -delete 2>/dev/null || true
