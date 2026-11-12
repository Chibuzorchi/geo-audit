PYTHON ?= python3.12
VENV ?= .venv
PY := $(VENV)/bin/python
CLI := $(VENV)/bin/geo-audit
OUT ?= .scratch/baseline
DEMO_OUT ?= .scratch/demo
RG_OUT ?= .scratch/red_green
STAMP := $(VENV)/.geo-audit-installed

.PHONY: install lint test baseline verify demo help

# Locked, isolated install; reruns only when the lock or project metadata change.
$(STAMP): requirements.lock pyproject.toml
	$(PYTHON) -m venv $(VENV)
	$(PY) -m pip install --only-binary=:all: -r requirements.lock
	$(PY) -m pip install --no-deps --no-build-isolation -e .
	touch $(STAMP)

install: $(STAMP)

lint: $(STAMP)
	$(PY) -m ruff check src tests scripts
	$(PY) -m ruff format --check src tests scripts

test: $(STAMP)
	$(PY) -m pytest tests

# Fresh output every run: synthetic data -> blind check + legacy ledger -> discovery.
baseline: $(STAMP)
	rm -rf $(OUT)
	$(CLI) generate --output $(OUT)/data
	$(CLI) check --input $(OUT)/data/SYNTHETIC_gps_pings.csv \
		--roads $(OUT)/data/roads.geojson --zone $(OUT)/data/zone.geojson \
		--output $(OUT)/results
	$(PY) scripts/discover_baseline.py --data $(OUT)/data --results $(OUT)/results \
		--expectations tests/expectations/analytic.json

# Strict legacy-red / corrected-green proof in fresh pytest subprocesses.
verify: $(STAMP)
	rm -rf $(RG_OUT)
	$(PY) scripts/verify_red_green.py --output $(RG_OUT)

# One command from a clean checkout: install, regenerate, compare, verify.
demo: $(STAMP)
	rm -rf $(DEMO_OUT)
	$(CLI) demo --output $(DEMO_OUT)

help:
	@echo 'install  locked .venv (python3.12)      lint     Ruff check + format'
	@echo 'test     all suites (corrected target)  baseline Phase 2 discovery into OUT'
	@echo 'verify   strict red/green into RG_OUT   demo     full reproducible demo into DEMO_OUT'
