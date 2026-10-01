FROM ghcr.io/astral-sh/uv:0.11.11 AS uv
FROM python:3.14-slim
COPY --from=uv /uv /usr/local/bin/uv
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy UV_HTTP_TIMEOUT=120 PATH="/app/.venv/bin:$PATH" PYTHONUNBUFFERED=1
WORKDIR /app
COPY pyproject.toml uv.lock ./
RUN --mount=type=cache,target=/root/.cache/uv uv sync --frozen --no-dev --no-install-project
COPY src ./src
COPY alembic ./alembic
COPY alembic.ini ./
RUN --mount=type=cache,target=/root/.cache/uv uv sync --frozen --no-dev && useradd --uid 10001 --create-home app
USER app
EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
