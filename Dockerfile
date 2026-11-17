# Imagens fixadas por digest: a tag sozinha pode mudar por baixo (OWASP AST07).
FROM python:3.15-slim@sha256:65a65fc7b30b06cb6df4930fd4650697cb23f4c2698ab81fc87e4b031bc36928

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PROJECT_ENVIRONMENT=/app/.venv \
    PATH=/app/.venv/bin:$PATH \
    KB_DIR=/app/knowledge_base

COPY --from=ghcr.io/astral-sh/uv:0.12.21@sha256:a7aed3216253ee804de3e2d8afa5073baa1a177335345d43845cd4165e43b711 /uv /usr/local/bin/uv

WORKDIR /app

# Dependências primeiro, para aproveitar cache de camada. --locked: só versões e hashes do uv.lock.
COPY pyproject.toml uv.lock README.md ./
RUN uv sync --locked --no-dev --no-install-project --no-cache

COPY src ./src
COPY knowledge_base ./knowledge_base
RUN uv sync --locked --no-dev --no-editable --no-cache

# Usuário sem privilégios; nenhum segredo entra na imagem (vêm do ambiente)
RUN useradd --create-home --uid 10001 app
USER 10001

EXPOSE 8000
HEALTHCHECK --interval=15s --timeout=3s --start-period=10s \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health/live')"

CMD ["uvicorn", "commerceops.api.main:app", "--host", "0.0.0.0", "--port", "8000", "--no-server-header"]
