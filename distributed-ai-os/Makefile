.PHONY: install test benchmark lint run-mock clean dashboard dashboard-dev dashboard-build

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

dashboard-build:
	cd apps/dashboard && npm install && npm run build

dashboard: install dashboard-build
	./scripts/run-dashboard.sh

dashboard-dev: install
	@echo "Run launcher in one terminal: .venv/bin/daios-launcher --root ."
	@echo "Run Vite dev in another: cd apps/dashboard && npm run dev"

clean:
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name .pytest_cache -exec rm -rf {} + 2>/dev/null || true
