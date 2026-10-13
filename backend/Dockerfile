# STAGE 1 - BUILD
FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim AS builder

WORKDIR /app

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy

COPY pyproject.toml uv.lock ./
RUN --mount=type=cache,target=/root/.cache/uv uv sync --frozen --no-dev --no-install-project

COPY . .
RUN --mount=type=cache,target=/root/.cache/uv uv sync --frozen --no-dev

# STAGE 2 - RUNTIME
FROM gcr.io/distroless/python3-debian12:nonroot AS runtime

WORKDIR /app

ENV PYTHONUNBUFFERED=1

COPY --from=builder /app/.venv/lib/python3.12/site-packages /app/.venv/lib/python3.12/site-packages
COPY --from=builder --chown=nonroot:nonroot /app /app

ENV PYTHONPATH="/app/.venv/lib/python3.11/site-packages:/app"

EXPOSE 8000

CMD ["/app/.venv/bin/uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]