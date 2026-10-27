"""Grava os chunks da base de conhecimento em kb.chunks (sem embeddings, por enquanto).

Uso: ADMIN_DATABASE_URL=postgresql://... python scripts/load_kb.py [--strict-legal]
A busca lexical (tsvector, 'portuguese') já funciona depois disto; os embeddings entram na etapa de RAG.
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

import psycopg

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from commerceops.knowledge.loader import load_knowledge_base  # noqa: E402
from commerceops.knowledge.store import write_chunks  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--strict-legal", action="store_true", help="recusa texto legal não verificado")
    args = ap.parse_args()
    url = os.environ.get("ADMIN_DATABASE_URL")
    if not url:
        print("defina ADMIN_DATABASE_URL", file=sys.stderr)
        return 2
    chunks = load_knowledge_base(strict_legal=args.strict_legal).chunks()
    with psycopg.connect(url) as conn:
        write_chunks(conn, chunks)
    print(f"kb.chunks: {len(chunks)} chunks gravados")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
