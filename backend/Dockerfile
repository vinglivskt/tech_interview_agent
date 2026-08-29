FROM python:3.12-slim-bookworm

COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

ENV UV_LINK_MODE=copy \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

WORKDIR /app

# Python deps first (better layer caching)
COPY pyproject.toml uv.lock README.md ./
RUN uv sync --frozen --no-dev

# App code and prompts
COPY backend/src ./src
COPY backend/prompts ./prompts

EXPOSE 8000

CMD ["uv", "run", "uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8000"]
