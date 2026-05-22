.PHONY: install dev test lint typecheck format clean docker-up docker-down analyze

PYTHON := python3.12
UV := uv

install:
	$(UV) sync --all-packages

dev:
	$(UV) sync --all-packages --dev

test:
	$(UV) run pytest tests/ -v

test-unit:
	$(UV) run pytest tests/unit/ -v

test-integration:
	$(UV) run pytest tests/integration/ -v -m integration

lint:
	$(UV) run ruff check packages/ tests/

format:
	$(UV) run ruff format packages/ tests/

typecheck:
	$(UV) run mypy packages/

clean:
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null; true
	find . -type d -name "*.egg-info" -exec rm -rf {} + 2>/dev/null; true
	find . -type d -name .mypy_cache -exec rm -rf {} + 2>/dev/null; true
	find . -type d -name htmlcov -exec rm -rf {} + 2>/dev/null; true
	rm -f .coverage 2>/dev/null; true

docker-up:
	docker compose up -d

docker-down:
	docker compose down -v

docker-build:
	docker compose build

analyze:
	@if [ -z "$(TICKER)" ]; then echo "Usage: make analyze TICKER=AAPL"; exit 1; fi
	$(UV) run python -m orchestrator.main analyze $(TICKER)

logs:
	docker compose logs -f

.DEFAULT_GOAL := help
help:
	@echo "Multi-Agent Financial Intelligence Hub"
	@echo ""
	@echo "  make install        Install all packages"
	@echo "  make dev            Install with dev dependencies"
	@echo "  make test           Run all tests"
	@echo "  make test-unit      Run unit tests only"
	@echo "  make test-integration  Run integration tests"
	@echo "  make lint           Lint code with ruff"
	@echo "  make format         Format code with ruff"
	@echo "  make typecheck      Type-check with mypy"
	@echo "  make docker-up      Start all services"
	@echo "  make docker-down    Stop all services"
	@echo "  make analyze TICKER=AAPL  Analyze a stock"
