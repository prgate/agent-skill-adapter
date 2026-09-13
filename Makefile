.DEFAULT_GOAL := help

PYTHON ?= python3
UV ?= uv

.PHONY: help
help: ## Show this help message
	@echo "Available targets:"
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-15s\033[0m %s\n", $$1, $$2}'

.PHONY: install
install: ## Install dependencies and package in editable mode
	$(UV) sync

.PHONY: lint
lint: ## Run linting and style checks
	$(UV) run ruff check .
	$(UV) run ruff format --check .

.PHONY: format
format: ## Automatically format and fix code style
	$(UV) run ruff check --fix .
	$(UV) run ruff format .

.PHONY: spec-schema
spec-schema: ## Regenerate the manifest JSON Schema from the Pydantic models
	$(UV) run python -c "from pathlib import Path; \
from agent_skill_adapter.specs.models import json_schema_text; \
p = Path('specs/schema/environmentspec.v1alpha1.json'); \
p.parent.mkdir(parents=True, exist_ok=True); \
p.write_text(json_schema_text(), encoding='utf-8')"

.PHONY: test
test: ## Run unit tests
	$(UV) run pytest

.PHONY: check
check: lint ## Run all quality gates (lint, typecheck, test)
	$(UV) run mypy src tests
	$(UV) run pytest

.PHONY: pre-commit-install
pre-commit-install: ## Install git hooks via pre-commit
	$(UV) run pre-commit install

.PHONY: pre-commit-run
pre-commit-run: ## Run pre-commit hooks against all files
	$(UV) run pre-commit run --all-files
