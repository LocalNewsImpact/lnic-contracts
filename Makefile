# The same checks CI runs, runnable before a push.
#
# This repository had none. Two applications import it, and its first two
# commits with CI attached went to main red: ruff had never run here,
# because there was nothing to run it with. Both failures were things a
# linter names in under a second.
#
# `make check` is the whole gate. scripts/setup-hooks.sh puts it on
# pre-push so it cannot be skipped by forgetting.

VENV := .venv
PY   := $(VENV)/bin/python
PIP  := $(VENV)/bin/pip

.DEFAULT_GOAL := help

$(VENV):
	python3 -m venv $(VENV)
	$(PIP) install -q --upgrade pip
	$(PIP) install -q -e ".[dev]"

.PHONY: setup
setup: $(VENV) ## Provision a new checkout
	@echo "Ready. 'make check' runs what CI runs."
	@echo "Run ./scripts/setup-hooks.sh once, to run it before every push."

.PHONY: lint
lint: $(VENV) ## ruff, the way CI runs it
	$(VENV)/bin/ruff check .

.PHONY: fmt
fmt: $(VENV) ## Apply what ruff can fix
	$(VENV)/bin/ruff check --fix .

.PHONY: test
test: $(VENV) ## The test suite, against the suite's coverage floor
# The floor this repository ships is the floor it is held to. Measured
# the way every consumer measures: pytest-cov writes coverage.xml, and
# lnic_contracts.coverage_floor reads it. No fail_under anywhere else.
	$(PY) -m pytest --cov --cov-report=xml --cov-report=term
	$(PY) -m lnic_contracts.coverage_floor coverage.xml

.PHONY: packaged
packaged: $(VENV) ## Does the built package carry the code? (CI runs this)
# The check that would have caught 4 September: datadesk's image reported
# lnic-contracts 0.2.0 and carried v0.1.0's code, and nothing anywhere
# installed the built package to notice.
	rm -rf dist
	$(PIP) install -q build
	$(PY) -m build --sdist --outdir dist
	rm -rf .packagecheck && python3 -m venv .packagecheck
	.packagecheck/bin/pip install -q dist/*.tar.gz
# From /tmp, so `src/` is not importable and this tests the package
# rather than the working tree.
	cd /tmp && $(CURDIR)/.packagecheck/bin/python $(CURDIR)/scripts/check_packaging.py
	rm -rf .packagecheck

.PHONY: check
check: lint test packaged ## Everything CI runs -- run before pushing

.PHONY: clean
clean:
	rm -rf $(VENV) .packagecheck build dist .pytest_cache .ruff_cache .coverage coverage.xml
	find . -name __pycache__ -type d -prune -exec rm -rf {} +

.PHONY: help
help:
	@grep -hE '^[a-z-]+:.*?## ' $(MAKEFILE_LIST) | awk 'BEGIN{FS=":.*?## "}{printf "  %-10s %s\n", $$1, $$2}'
