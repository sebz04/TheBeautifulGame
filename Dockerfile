# MatchMind API + website in one image (TASK-24). The API serves the built site, the
# REST/SSE endpoints, and the MCP stats server at /mcp.

# 1. The website
FROM node:22-bookworm-slim AS web
WORKDIR /web
COPY web/package.json web/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY web/ ./
RUN npm run build

# 2. The API, with the Azure extras and Microsoft's ODBC driver for Azure SQL
FROM python:3.12-slim-bookworm
RUN apt-get update \
    && apt-get install -y --no-install-recommends curl gnupg ca-certificates \
    && curl -fsSL https://packages.microsoft.com/keys/microsoft.asc | gpg --dearmor -o /usr/share/keyrings/microsoft.gpg \
    && echo "deb [signed-by=/usr/share/keyrings/microsoft.gpg] https://packages.microsoft.com/debian/12/prod bookworm main" \
       > /etc/apt/sources.list.d/microsoft.list \
    && apt-get update \
    && ACCEPT_EULA=Y apt-get install -y --no-install-recommends msodbcsql18 unixodbc \
    && apt-get purge -y curl gnupg && apt-get autoremove -y && rm -rf /var/lib/apt/lists/*
COPY --from=ghcr.io/astral-sh/uv:0.9.7 /uv /bin/uv
WORKDIR /app
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy
COPY pyproject.toml uv.lock README.md ./
RUN uv sync --locked --no-dev --extra azure --no-install-project
COPY src ./src
COPY data/models ./data/models
# For the offline local demo (docker compose): the 8 storylines and the seed script.
COPY scenarios ./scenarios
COPY scripts/seed_demo.py ./scripts/seed_demo.py
RUN uv sync --locked --no-dev --extra azure
COPY --from=web /web/dist ./web/dist
ENV PATH="/app/.venv/bin:$PATH" PYTHONUNBUFFERED=1
RUN useradd --create-home app && mkdir /data && chown -R app /app /data
USER app
EXPOSE 8000
CMD ["uvicorn", "matchmind.api.app:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers", "--forwarded-allow-ips", "*"]
