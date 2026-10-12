FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim

WORKDIR /app

ENV PYTHONUNBUFFERED=1

COPY pyproject.toml ./

RUN uv lock
RUN uv sync --no-dev

COPY . .

EXPOSE 8001

CMD ["uv", "run", "uvicorn", "bot_service.app:app", "--host", "0.0.0.0", "--port", "8001"]