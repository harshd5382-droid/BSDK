.PHONY: install test benchmark benchmark-with-worker benchmark-without-worker benchmark-compare lint run-mock clean dashboard dashboard-dev dashboard-build

VENV := .venv
PY := $(VENV)/bin/python
PIP := $(VENV)/bin/pip

install:
	./scripts/install-dev.sh

test: install
	$(VENV)/bin/pytest tests/ -v

benchmark: install
	$(PY) benchmarks/run_benchmark.py --url http://127.0.0.1:8000 -n 20

# Step 1: run while the worker PC is connected (coordinator + remote RPC worker).
benchmark-with-worker: install
	$(PY) benchmarks/run_benchmark.py --url http://127.0.0.1:8000 -n 5 \
		--label with-worker -o benchmarks/results/with-worker.json

# Step 2: stop the node, restart the coordinator alone (no peer), then run this.
benchmark-without-worker: install
	$(PY) benchmarks/run_benchmark.py --url http://127.0.0.1:8000 -n 5 \
		--label without-worker -o benchmarks/results/without-worker.json

# Step 3: print the time difference between the two runs above.
benchmark-compare:
	$(PY) benchmarks/compare_worker.py \
		benchmarks/results/with-worker.json \
		benchmarks/results/without-worker.json

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
