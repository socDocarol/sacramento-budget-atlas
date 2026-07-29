FROM ghcr.io/astral-sh/uv:0.9.18 AS uv

FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    BUDGET_CACHE_DIR=/var/cache/sacramento-budget \
    BUDGET_CACHE_TTL_SECONDS=86400 \
    LOG_LEVEL=INFO

COPY --from=uv /uv /uvx /bin/

WORKDIR /app

COPY pyproject.toml uv.lock README.md ./
RUN uv sync --frozen --no-dev --no-install-project

COPY app.py _brand.yml ./
COPY budget_app ./budget_app
COPY www ./www

RUN groupadd --system budgetapp \
    && useradd --system --gid budgetapp --home-dir /app budgetapp \
    && mkdir -p /var/cache/sacramento-budget \
    && chown -R budgetapp:budgetapp /app /var/cache/sacramento-budget

USER budgetapp

ENV PATH="/app/.venv/bin:${PATH}"

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=30s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/', timeout=3)"

CMD ["shiny", "run", "--host", "0.0.0.0", "--port", "8000", "app.py"]
