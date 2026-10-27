import os

# Valores só de teste. Definidos antes de importar a aplicação.
os.environ.setdefault("DATABASE_URL", "postgresql://unused@localhost:1/unused")
os.environ.setdefault("ORDER_ID_HMAC_KEY", "chave-de-teste")
os.environ.setdefault("LANGFUSE_TRACING_ENABLED", "false")
