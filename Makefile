PYTHON ?= python3.12
VENV ?= .venv
PY := $(VENV)/bin/python
CLI := $(VENV)/bin/geo-audit
OUT ?= .scratch/baseline

.PHONY: install lint test baseline help
install:
	$(PYTHON) -m venv $(VENV)
	$(PY) -m pip install --only-binary=:all: -r requirements.lock
	$(PY) -m pip install --no-deps --no-build-isolation -e .

lint:
	$(PY) -m ruff check src tests scripts
	$(PY) -m ruff format --check src tests scripts

test:
	$(PY) -m pytest tests

# Fresh output every run: synthetic data -> blind check + legacy ledger -> discovery.
baseline:
	rm -rf $(OUT)
	$(CLI) generate --output $(OUT)/data
	$(CLI) check --input $(OUT)/data/SYNTHETIC_gps_pings.csv \
		--roads $(OUT)/data/roads.geojson --zone $(OUT)/data/zone.geojson \
		--output $(OUT)/results
	$(PY) scripts/discover_baseline.py --data $(OUT)/data --results $(OUT)/results \
		--expectations tests/expectations/analytic.json

help:
	@echo 'install: locked install; lint: Ruff; test: all suites;'
	@echo 'baseline: generate synthetic data, run checker + legacy, measure discrepancies (OUT=dir)'
