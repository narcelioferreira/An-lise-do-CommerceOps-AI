"""Grava os chunks da base de conhecimento em kb.chunks.

Uso: ADMIN_DATABASE_URL=postgresql://... python scripts/load_kb.py
Texto legal não verificado com a fonte oficial é recusado: nunca chega ao RAG.
Com EMBEDDING_BASE_URL e EMBEDDING_MODEL, grava também os embeddings (busca vetorial e híbrida).
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import psycopg

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from commerceops.config import get_settings  # noqa: E402
from commerceops.knowledge.loader import load_knowledge_base  # noqa: E402
from commerceops.knowledge.store import embedding_text, write_chunks  # noqa: E402
from commerceops.llm import make_embedder  # noqa: E402
from commerceops.observability import init_langfuse  # noqa: E402


def main() -> int:
    url = os.environ.get("ADMIN_DATABASE_URL")
    if not url:
        print("defina ADMIN_DATABASE_URL", file=sys.stderr)
        return 2
    chunks = load_knowledge_base(strict_legal=True).chunks()
    settings = get_settings()
    init_langfuse(settings)  # langfuse.openai instrumenta o SDK do OpenAI, inclusive embeddings
    embed = make_embedder(settings)
    embeddings = embed([embedding_text(c) for c in chunks]) if embed else None
    with psycopg.connect(url) as conn:
        write_chunks(conn, chunks, embeddings, settings.embedding_model)
    model = settings.embedding_model if embed else "não"
    print(f"kb.chunks: {len(chunks)} chunks gravados, embeddings: {model}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
