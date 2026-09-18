.PHONY: postgres install seed test mcp api frontend demo

postgres:
	docker compose up -d postgres

install:
	python3 -m venv backend/.venv
	backend/.venv/bin/pip install -r backend/requirements.txt
	cd frontend && npm install

seed:
	cd backend && .venv/bin/python -m app.seed

test:
	cd backend && .venv/bin/pytest -q

mcp:
	cd backend && .venv/bin/python -m app.mcp_server --transport http

api:
	cd backend && .venv/bin/python -m app.main

frontend:
	cd frontend && npm run dev

demo:
	cd backend && .venv/bin/python -m app.demo_mcp_client --in-process
