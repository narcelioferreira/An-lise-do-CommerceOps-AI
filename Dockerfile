FROM python:3.12-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    KB_DIR=/app/knowledge_base

COPY --from=ghcr.io/astral-sh/uv:0.8.17 /uv /usr/local/bin/uv

WORKDIR /app

# Dependências primeiro, para aproveitar cache de camada
COPY pyproject.toml uv.lock* README.md ./
RUN uv pip install --system --no-cache -r pyproject.toml

COPY src ./src
COPY knowledge_base ./knowledge_base
RUN uv pip install --system --no-cache --no-deps .

# Usuário sem privilégios; nenhum segredo entra na imagem (vêm do ambiente)
RUN useradd --create-home --uid 10001 app
USER app

EXPOSE 8000
HEALTHCHECK --interval=15s --timeout=3s --start-period=10s \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health/live')"

CMD ["uvicorn", "commerceops.api.main:app", "--host", "0.0.0.0", "--port", "8000"]
