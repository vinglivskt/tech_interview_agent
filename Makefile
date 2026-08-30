.PHONY: help install dev-backend dev-frontend build-frontend build test lint clean db-migrate db-revision

help:
	@echo "Available targets:"
	@echo "  install          Install Python + Node dependencies"
	@echo "  dev-backend      Run backend locally (http://localhost:8000)"
	@echo "  dev-frontend     Run frontend dev server (http://localhost:3000)"
	@echo "  build-frontend   Build frontend into backend/static/"
	@echo "  test             Run all tests"
	@echo "  lint             ruff + tsc"
	@echo "  clean            Remove build artifacts"
	@echo "  db-migrate       Apply Alembic migrations"
	@echo "  db-revision      Create a new Alembic revision (use msg=\"...\")"

install:
	uv sync
	cd frontend && npm install

dev-backend:
	cd backend && uv run uvicorn src.main:app --host 0.0.0.0 --port 8000 --reload

dev-frontend:
	cd frontend && npm run dev -- --host 0.0.0.0

build-frontend:
	cd frontend && npm run build
	rm -rf backend/static
	mkdir -p backend/static
	cp -r frontend/dist/* backend/static/

test:
	uv run pytest tests/ -v

lint:
	uv run ruff check backend/ tests/
	cd frontend && npx tsc --noEmit

db-migrate:
	cd backend && uv run alembic upgrade head

db-revision:
	cd backend && uv run alembic revision --autogenerate -m "$(msg)"

clean:
	rm -rf backend/static
	rm -rf frontend/dist
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name .pytest_cache -exec rm -rf {} + 2>/dev/null || true
