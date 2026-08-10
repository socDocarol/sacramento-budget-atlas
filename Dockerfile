FROM ghcr.io/astral-sh/uv:0.12.0@sha256:606e70c71c852d03f611b1e56a195d08648507018a7057fab82c4974c4eae105 AS uv

FROM python:3.12.13-slim-bookworm@sha256:4766d8b510c428e595d74b9cc5bbb2fae8e26316fffb4adc89908d79aacd58a2 AS builder

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_NO_CACHE=1 \
    UV_PYTHON_DOWNLOADS=never

WORKDIR /app

COPY --from=uv /uv /bin/uv
COPY pyproject.toml uv.lock README.md ./
RUN uv sync --frozen --no-dev --no-install-project

FROM python:3.12.13-slim-bookworm@sha256:4766d8b510c428e595d74b9cc5bbb2fae8e26316fffb4adc89908d79aacd58a2 AS runtime

ENV PATH="/app/.venv/bin:${PATH}" \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONFAULTHANDLER=1 \
    PYTHONUNBUFFERED=1 \
    BUDGET_CACHE_DIR=/var/cache/sacramento-budget \
    BUDGET_CACHE_TTL_SECONDS=86400 \
    LOG_LEVEL=INFO

WORKDIR /app

RUN groupadd --gid 10001 budgetapp \
    && useradd --uid 10001 --gid 10001 --no-create-home \
        --home-dir /nonexistent --shell /usr/sbin/nologin budgetapp \
    && install -d -o budgetapp -g budgetapp -m 0750 /var/cache/sacramento-budget

COPY --from=builder /app/.venv /app/.venv
COPY app.py _brand.yml ./
COPY budget_app ./budget_app
COPY www ./www

USER 10001:10001

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=60s --retries=3 \
    CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health/live', timeout=3)"]

STOPSIGNAL SIGTERM

CMD ["uvicorn", "app:asgi_app", "--host", "0.0.0.0", "--port", "8000", "--no-server-header"]
