.PHONY: help install dev-backend dev-frontend build-frontend build test lint clean

help:
	@echo "Available targets:"
	@echo "  install          Install Python + Node dependencies"
	@echo "  dev-backend      Run backend locally (http://localhost:8000)"
	@echo "  dev-frontend     Run frontend dev server (http://localhost:3000)"
	@echo "  build-frontend   Build frontend into backend/static/"
	@echo "  test             Run all tests"
	@echo "  lint             Run ruff + tsc"
	@echo "  clean            Remove build artifacts"

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

clean:
	rm -rf backend/static
	rm -rf frontend/dist
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name .pytest_cache -exec rm -rf {} + 2>/dev/null || true
