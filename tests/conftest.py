import os

# Valores só de teste. Definidos antes de importar a aplicação.
os.environ.setdefault("DATABASE_URL", "postgresql://unused@localhost:1/unused")
os.environ.setdefault("ORDER_ID_HMAC_KEY", "chave-de-teste")
os.environ.setdefault("LANGFUSE_TRACING_ENABLED", "false")

from commerceops.config import Settings  # noqa: E402

# Os testes não podem depender do .env de quem roda: com chaves reais nele, chamariam a rede.
Settings.model_config["env_file"] = None
