FROM python:3.12-slim-bookworm AS build
COPY --from=ghcr.io/astral-sh/uv:0.10.12 /uv /usr/local/bin/uv
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy UV_PYTHON_DOWNLOADS=never
WORKDIR /app
COPY pyproject.toml uv.lock ./
RUN uv sync --locked --no-dev --no-install-project
COPY src ./src
RUN uv sync --locked --no-dev --no-editable

FROM python:3.12-slim-bookworm
RUN useradd --create-home --uid 1000 app
WORKDIR /app
COPY --from=build /app/.venv /app/.venv
ENV PATH="/app/.venv/bin:$PATH" PYTHONUNBUFFERED=1 DB_PATH=/app/data/tldr.db
RUN mkdir -p /app/data && chown app:app /app/data
USER app
EXPOSE 8000
CMD ["tldr-linebot"]
