"""Busca na base de conhecimento: lexical, vetorial e híbrida.

A busca nunca decide nada: ela fornece contexto ao gerador e é medida na avaliação. As seções que
fundamentam a decisão vêm das regras em código (domain/), não do ranking.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import date
from enum import StrEnum
from typing import Protocol

RRF_K = 60  # constante usual da Reciprocal Rank Fusion; amortece a diferença entre as primeiras posições


class Method(StrEnum):
    LEXICAL = "lexical"
    VECTOR = "vector"
    HYBRID = "hybrid"


@dataclass(frozen=True)
class ChunkRow:
    chunk_id: str
    doc_id: str
    version: str | None
    source_type: str
    title: str
    escalation: str
    text: str


class KnowledgeRepository(Protocol):
    def lexical(self, query: str, day: date, intents: list[str] | None, k: int) -> list[ChunkRow]: ...
    def vector(
        self, embedding: list[float], day: date, intents: list[str] | None, k: int
    ) -> list[ChunkRow]: ...
    def get_chunks(self, chunk_ids: list[str]) -> list[ChunkRow]: ...


Embedder = Callable[[list[str]], list[list[float]]]


def rrf(rankings: list[list[ChunkRow]], k: int) -> list[ChunkRow]:
    """Funde rankings por posição (1 / (RRF_K + posição)). Não depende da escala dos escores."""
    scores: dict[str, float] = {}
    rows: dict[str, ChunkRow] = {}
    for ranking in rankings:
        for pos, row in enumerate(ranking, start=1):
            scores[row.chunk_id] = scores.get(row.chunk_id, 0.0) + 1 / (RRF_K + pos)
            rows[row.chunk_id] = row
    return [rows[cid] for cid in sorted(scores, key=lambda c: (-scores[c], c))[:k]]


class Retriever:
    def __init__(self, repo: KnowledgeRepository, embed: Embedder | None = None) -> None:
        self.repo = repo
        self.embed = embed

    def search(
        self,
        query: str,
        *,
        day: date,
        method: Method = Method.HYBRID,
        intents: list[str] | None = None,
        k: int = 5,
    ) -> list[ChunkRow]:
        """`day` é a data da compra: só a versão de política vigente nela é candidata (D3)."""
        if method is not Method.LEXICAL and self.embed is None:
            raise ValueError(f"busca {method} exige embeddings configurados")
        if method is Method.LEXICAL:
            return self.repo.lexical(query, day, intents, k)
        embedding = self.embed([query])[0]  # type: ignore[misc]
        if method is Method.VECTOR:
            return self.repo.vector(embedding, day, intents, k)
        # Candidatos extras dos dois lados para a fusão ter material
        return rrf(
            [self.repo.lexical(query, day, intents, 2 * k), self.repo.vector(embedding, day, intents, 2 * k)],
            k,
        )
