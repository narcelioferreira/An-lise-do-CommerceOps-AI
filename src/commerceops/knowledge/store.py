"""Gravação dos chunks em kb.chunks (sem embeddings por enquanto; entram na etapa de RAG)."""

from __future__ import annotations

import psycopg

from commerceops.knowledge.models import Chunk

COLUMNS = [
    "chunk_id",
    "doc_id",
    "version",
    "source_type",
    "fictional",
    "title",
    "effective_from",
    "effective_until",
    "intents",
    "escalation",
    "text",
]


def write_chunks(conn: psycopg.Connection, chunks: list[Chunk]) -> None:
    sql = f"INSERT INTO kb.chunks ({', '.join(COLUMNS)}) VALUES ({', '.join(['%s'] * len(COLUMNS))})"
    with conn.transaction():
        conn.execute("TRUNCATE kb.chunks")
        with conn.cursor() as cur:
            cur.executemany(sql, [tuple(getattr(c, col) for col in COLUMNS) for c in chunks])
