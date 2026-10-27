import os
import socket

import pytest

# Testes nunca chamam LLM, embeddings nem Langfuse reais (consumo de tokens e dados). Credenciais
# exportadas no shell de quem roda são descartadas antes de importar a aplicação.
for name in list(os.environ):
    if name.startswith(("LLM_", "EMBEDDING_", "LANGFUSE_")):
        del os.environ[name]

# Valores só de teste. Definidos antes de importar a aplicação.
os.environ.setdefault("DATABASE_URL", "postgresql://unused@localhost:1/unused")
os.environ.setdefault("ORDER_ID_HMAC_KEY", "chave-de-teste")
os.environ["LANGFUSE_TRACING_ENABLED"] = "false"

from commerceops.config import Settings  # noqa: E402

# Os testes não podem depender do .env de quem roda: com chaves reais nele, chamariam a rede.
Settings.model_config["env_file"] = None

LOCAL_HOSTS = {"127.0.0.1", "::1", "localhost"}


@pytest.fixture(autouse=True)
def _sem_rede_externa(monkeypatch):
    """Trava: qualquer conexão fora do localhost falha na hora, em vez de gastar tokens."""
    connect = socket.socket.connect

    def guarded(sock, address):
        host = address[0] if isinstance(address, tuple) else None
        if host is not None and host not in LOCAL_HOSTS:
            raise ConnectionRefusedError(f"teste tentou acessar a rede externa: {host}")
        return connect(sock, address)

    monkeypatch.setattr(socket.socket, "connect", guarded)
