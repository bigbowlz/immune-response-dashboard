# Immune Response Dashboard.
#   make setup      install Python deps into .venv, install frontend packages, build the frontend
#   make pipeline   python load_data.py, then python -m analysis.pipeline  ->  cell_counts.db
#   make dashboard  serve API + dashboard on http://localhost:$(PORT)  (PORT=8001 make dashboard to change)
# Override the interpreter with PYTHON=... ; force a frontend rebuild with REBUILD=1.

VENV   ?= .venv
PYTHON ?= $(VENV)/bin/python
PORT   ?= 8000

.PHONY: setup pipeline dashboard

setup:
	@command -v npm >/dev/null 2>&1 || { echo "npm not found. Install Node 20+ (https://nodejs.org) or open this repo in GitHub Codespaces, whose devcontainer includes Node."; exit 1; }
	@test -x "$(PYTHON)" || python3 -m venv "$(VENV)"
	"$(PYTHON)" -m pip install --quiet --upgrade pip
	"$(PYTHON)" -m pip install --quiet -r requirements.txt -r requirements-pipeline.txt -r requirements-dev.txt
	npm ci --prefix frontend
	npm run build --prefix frontend

pipeline:
	@test -x "$(PYTHON)" || { echo "$(PYTHON) not found. Run 'make setup' first."; exit 1; }
	"$(PYTHON)" load_data.py
	"$(PYTHON)" -m analysis.pipeline

dashboard:
	@test -x "$(PYTHON)" || { echo "$(PYTHON) not found. Run 'make setup' first."; exit 1; }
	@test -f cell_counts.db || echo "Note: cell_counts.db not found. The dashboard will ask you to run 'make pipeline'."
	@if [ ! -d frontend/dist ] || [ -n "$(REBUILD)" ]; then \
		test -d frontend/node_modules || { echo "frontend/node_modules missing. Run 'make setup' first."; exit 1; }; \
		npm run build --prefix frontend; \
	fi
	@echo "Dashboard: http://localhost:$(PORT)  (Ctrl+C to stop; PORT=8001 make dashboard to use another port)"
	"$(PYTHON)" -m uvicorn server.app:app --host 0.0.0.0 --port $(PORT)
