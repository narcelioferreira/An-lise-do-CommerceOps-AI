"""Gravação dos chunks em kb.chunks, com embeddings quando houver modelo configurado."""

from __future__ import annotations

import psycopg
from psycopg import sql

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
    "embedding",
    "embedding_model",
]


def embedding_text(c: Chunk) -> str:
    return f"{c.title}\n\n{c.text}"


def write_chunks(
    conn: psycopg.Connection,
    chunks: list[Chunk],
    embeddings: list[list[float]] | None = None,
    model: str | None = None,
) -> None:
    vectors = [str(e) for e in embeddings] if embeddings else [None] * len(chunks)
    rows = [
        (*(getattr(c, col) for col in COLUMNS[:-2]), vec, model if vec else None)
        for c, vec in zip(chunks, vectors, strict=True)
    ]
    insert = sql.SQL("INSERT INTO kb.chunks ({}) VALUES ({})").format(
        sql.SQL(", ").join(map(sql.Identifier, COLUMNS)), sql.SQL(", ").join(sql.Placeholder() * len(COLUMNS))
    )
    with conn.transaction():
        conn.execute("TRUNCATE kb.chunks")
        with conn.cursor() as cur:
            cur.executemany(insert, rows)
