# Runix Decision Engine — the Makefile is the interface.
# `make install && make run` should work from a clean checkout.

# Use uv if available (fast), otherwise fall back to python -m venv + pip.
UV := $(shell command -v uv 2>/dev/null)
VENV := .venv
PY := $(VENV)/bin/python
DATASET := data/Runix_Logistics_Engine_Scenario_Dataset.xlsx

.DEFAULT_GOAL := help
.PHONY: help install run run-verbose explain dashboard test lint clean

help:  ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) \
		| awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-14s\033[0m %s\n", $$1, $$2}'

install:  ## Create a virtualenv and install the package (with dashboard + dev extras)
ifneq ($(UV),)
	uv venv --python 3.11 $(VENV)
	uv pip install --python $(PY) -e ".[dashboard,dev]"
else
	python3 -m venv $(VENV)
	$(PY) -m pip install --upgrade pip
	$(PY) -m pip install -e ".[dashboard,dev]"
endif
	@echo "\nInstalled. Try:  make run"

run:  ## Run the engine on the bundled scenario and print the WhatsApp alert
	$(PY) -m runix --dataset "$(DATASET)" --pretty

run-verbose:  ## Run with the full reasoning trace (capacity, risk, cost curve, baselines)
	$(PY) -m runix --dataset "$(DATASET)" --pretty --verbose

explain:  ## Emit the full machine-readable decision report (alert + all intermediates)
	$(PY) -m runix --dataset "$(DATASET)" --report --pretty

dashboard:  ## Launch the interactive Streamlit decision dashboard
	$(PY) -m streamlit run app/dashboard.py

test:  ## Run the test suite
	$(PY) -m pytest

lint:  ## Lint with ruff
	$(PY) -m ruff check src tests app

clean:  ## Remove the venv and caches
	rm -rf $(VENV) .pytest_cache .ruff_cache
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
