from datetime import date

import pytest

from commerceops.knowledge.retrieval import ChunkRow, Method, Retriever, rrf

DAY = date(2018, 3, 1)


def row(cid: str) -> ChunkRow:
    return ChunkRow(cid, cid.split("@")[0][:11], "1.0", "fictional_policy", cid, "none", "texto")


class FakeRepo:
    def __init__(self):
        self.calls = []

    def lexical(self, query, day, intents, k):
        self.calls.append(("lexical", k))
        return [row("A"), row("B"), row("C")][:k]

    def vector(self, embedding, day, intents, k):
        self.calls.append(("vector", k))
        return [row("C"), row("A"), row("D")][:k]

    def get_chunks(self, chunk_ids):
        return [row(c) for c in chunk_ids]


def test_rrf_premia_quem_aparece_bem_nos_dois_rankings():
    fused = rrf([[row("A"), row("B"), row("C")], [row("C"), row("A"), row("D")]], k=4)
    assert [r.chunk_id for r in fused] == ["A", "C", "B", "D"]


def test_rrf_desempata_de_forma_deterministica():
    assert [r.chunk_id for r in rrf([[row("B")], [row("A")]], k=2)] == ["A", "B"]


def test_hibrida_busca_candidatos_extras_e_corta_em_k():
    repo = FakeRepo()
    hits = Retriever(repo, embed=lambda texts: [[0.0]] * len(texts)).search("q", day=DAY, k=2)
    assert repo.calls == [("lexical", 4), ("vector", 4)]
    assert [h.chunk_id for h in hits] == ["A", "C"]


@pytest.mark.parametrize("method", [Method.VECTOR, Method.HYBRID])
def test_sem_embeddings_so_lexical(method):
    r = Retriever(FakeRepo())
    assert [h.chunk_id for h in r.search("q", day=DAY, method=Method.LEXICAL, k=1)] == ["A"]
    with pytest.raises(ValueError, match="exige embeddings"):
        r.search("q", day=DAY, method=method)
