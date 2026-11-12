PYTHON ?= python3.12
VENV ?= .venv
PY := $(VENV)/bin/python

.PHONY: install lint test help
install:
	$(PYTHON) -m venv $(VENV)
	$(PY) -m pip install --only-binary=:all: -r requirements.lock
	$(PY) -m pip install --no-deps --no-build-isolation -e .

lint:
	$(PY) -m ruff check src tests
	$(PY) -m ruff format --check src tests

test:
	$(PY) -m pytest tests/unit

help:
	@echo 'install: isolated locked installation; lint: Ruff; test: Phase 1 unit suite'
