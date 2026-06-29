.PHONY: install test benchmark lint run-mock clean

VENV := .venv
PY := $(VENV)/bin/python
PIP := $(VENV)/bin/pip

install:
	./scripts/install-dev.sh

test: install
	$(VENV)/bin/pytest tests/ -v

benchmark: install
	$(PY) benchmarks/run_benchmark.py --url http://127.0.0.1:8000 -n 20

lint: install
	$(VENV)/bin/ruff check packages/ apps/ tests/ benchmarks/

run-mock: install
	./scripts/run-mock-cluster.sh

clean:
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name .pytest_cache -exec rm -rf {} + 2>/dev/null || true
