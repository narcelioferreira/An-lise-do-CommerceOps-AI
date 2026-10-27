"""Integração com Postgres + pgvector. Roda no CI (serviço) ou localmente com o compose:

    pytest -m integration

Exige ADMIN_DATABASE_URL (superusuário) e DATABASE_URL (usuário da aplicação) apontando para um
banco criado com db/init/. Carrega um mini-dataset sintético, nunca os CSVs reais.
"""

import json
import os
import re
import zlib
from datetime import date, datetime
from pathlib import Path

import psycopg
import pytest
from psycopg_pool import ConnectionPool

from commerceops.data.load import load, prepare
from commerceops.db import PostgresKnowledgeRepository, PostgresOrderRepository
from commerceops.knowledge.loader import load_knowledge_base
from commerceops.knowledge.retrieval import Method, Retriever
from commerceops.knowledge.store import embedding_text, write_chunks
from commerceops.tools.orders import OrderAccessDenied, get_order_summary, verify_customer

pytestmark = pytest.mark.integration

ADMIN = os.environ.get("ADMIN_DATABASE_URL")
APP = os.environ.get("DATABASE_URL", "")
if not ADMIN or "unused" in APP:
    pytest.skip("ADMIN_DATABASE_URL e DATABASE_URL não configurados", allow_module_level=True)

KEY = "chave-de-teste"
OID_1 = "1" * 32
OID_2 = "2" * 32

CSV = {
    "olist_customers_dataset.csv": (
        '"customer_id","customer_unique_id","customer_zip_code_prefix","customer_city","customer_state"\n'
        '"c1","u1","09790",sao bernardo do campo,SP\n'
        '"c2","u2","14409",franca,SP\n'
    ),
    "olist_sellers_dataset.csv": (
        '"seller_id","seller_zip_code_prefix","seller_city","seller_state"\n"s1","01001",sao paulo,SP\n'
    ),
    "product_category_name_translation.csv": (
        "﻿product_category_name,product_category_name_english\nbeleza_saude,health_beauty\n"
    ),
    "olist_products_dataset.csv": (
        '"product_id","product_category_name","product_name_lenght","product_description_lenght",'
        '"product_photos_qty","product_weight_g","product_length_cm","product_height_cm","product_width_cm"\n'
        '"p1","beleza_saude",40,300,1,500,20,10,15\n'
        '"p2",,,,,,,,\n'  # 610 produtos reais sem categoria nem medidas
    ),
    "olist_orders_dataset.csv": (
        '"order_id","customer_id","order_status","order_purchase_timestamp","order_approved_at",'
        '"order_delivered_carrier_date","order_delivered_customer_date","order_estimated_delivery_date"\n'
        f'"{OID_1}","c1",delivered,2017-12-20 10:00:00,2017-12-20 11:00:00,2017-12-22 09:00:00,'
        "2018-01-05 18:00:00,2018-01-03 00:00:00\n"
        f'"{OID_2}","c2",canceled,2018-01-01 10:00:00,,,2018-01-09 09:00:00,2018-01-20 00:00:00\n'
    ),
    "olist_order_items_dataset.csv": (
        '"order_id","order_item_id","product_id","seller_id","shipping_limit_date","price","freight_value"\n'
        f'"{OID_1}",1,"p1","s1",2017-12-26 00:00:00,100.00,10.00\n'
    ),
    "olist_order_payments_dataset.csv": (
        '"order_id","payment_sequential","payment_type","payment_installments","payment_value"\n'
        f'"{OID_1}",1,voucher,1,30.00\n"{OID_1}",2,credit_card,3,80.00\n'
    ),
    "olist_order_reviews_dataset.csv": (
        '"review_id","order_id","review_score","review_comment_title","review_comment_message",'
        '"review_creation_date","review_answer_timestamp"\n'
        f'"r1","{OID_1}",5,,"chegou certinho",2018-01-06 01:00:00,2018-01-07 10:00:00\n'
        f'"r1","{OID_2}",1,,,2018-01-10 00:00:00,2018-01-11 10:00:00\n'
    ),
}


def fake_embed(texts: list[str]) -> list[list[float]]:
    """Saco de palavras em 1024 posições: determinístico e suficiente para testar o caminho vetorial."""
    out = []
    for text in texts:
        v = [0.0] * 1024
        for word in re.findall(r"\w+", text.lower()):
            v[zlib.crc32(word.encode()) % 1024] += 1.0
        out.append(v)
    return out


@pytest.fixture(scope="module")
def loaded(tmp_path_factory):
    raw: Path = tmp_path_factory.mktemp("raw")
    for name, content in CSV.items():
        (raw / name).write_text(content, encoding="utf-8")
    with psycopg.connect(ADMIN) as conn:
        load(conn, prepare(raw))
        chunks = load_knowledge_base().chunks()
        write_chunks(conn, chunks, fake_embed([embedding_text(c) for c in chunks]), "fake-bow")


@pytest.fixture(scope="module")
def repo(loaded):
    pool = ConnectionPool(APP, min_size=1, max_size=2, open=True)
    yield PostgresOrderRepository(pool)
    pool.close()


def test_carga_preserva_zero_do_cep_e_trata_avaliacoes(loaded):
    with psycopg.connect(ADMIN) as conn:
        assert (
            conn.execute(
                "SELECT customer_zip_code_prefix FROM olist.customers WHERE customer_id='c1'"
            ).fetchone()[0]
            == "09790"
        )
        rows = conn.execute(
            "SELECT review_creation_date, review_id_duplicate FROM olist.order_reviews ORDER BY review_row_id"
        ).fetchall()
    assert rows == [(date(2018, 1, 6), True), (date(2018, 1, 10), True)]


def test_ferramentas_contra_o_banco(repo):
    customer = verify_customer(repo, OID_1, "09790", hmac_key=KEY)
    s = get_order_summary(repo, customer, OID_1, date(2018, 1, 25), hmac_key=KEY)
    assert s.days_since_delivery == 20 and s.days_late == 2
    assert str(s.total_paid) == "110.00"
    with pytest.raises(OrderAccessDenied):
        get_order_summary(repo, customer, OID_2, date(2018, 1, 25), hmac_key=KEY)


def test_acoes_ficam_registradas_sem_id_cru(repo):
    with psycopg.connect(ADMIN) as conn:
        hashes = [r[0] for r in conn.execute("SELECT order_id_hash FROM sim.agent_actions").fetchall()]
    assert hashes and OID_1 not in hashes


@pytest.mark.parametrize(
    "sql",
    [
        "INSERT INTO olist.sellers VALUES ('x', '00000', 'x', 'XX')",  # dado real é somente leitura
        "UPDATE olist.orders SET order_status = 'delivered'",
        "DELETE FROM sim.agent_actions",  # trilha de auditoria não se apaga
        "TRUNCATE kb.chunks",  # aplicação não altera a base de conhecimento
        "CREATE TABLE public.x (id int)",
    ],
)
def test_usuario_da_aplicacao_tem_privilegio_minimo(loaded, sql):
    with psycopg.connect(APP) as conn, pytest.raises(psycopg.errors.InsufficientPrivilege):
        conn.execute(sql)


def test_busca_lexical_em_portugues_encontra_politica(loaded):
    with psycopg.connect(APP) as conn:
        top = conn.execute(
            """
            SELECT chunk_id FROM kb.chunks
            WHERE tsv @@ plainto_tsquery('portuguese', %s)
            ORDER BY ts_rank(tsv, plainto_tsquery('portuguese', %s)) DESC LIMIT 3
            """,
            ("desistir arrependimento", "desistir arrependimento"),
        ).fetchall()
    assert any(c[0].startswith(("POL-DEV-001", "LEG-CDC-049")) for c in top)


@pytest.fixture(scope="module")
def retriever(loaded):
    pool = ConnectionPool(APP, min_size=1, max_size=2, open=True)
    yield Retriever(PostgresKnowledgeRepository(pool), fake_embed)
    pool.close()


def test_busca_lexical_liga_termos_por_ou(retriever):
    # mensagem longa com palavras que não estão em nenhum chunk: com E não acharia nada
    msg = "oi, boa tarde!! me arrependi da compra do liquidificador azul, quero desistir"
    hits = retriever.search(msg, day=date(2018, 3, 1), method=Method.LEXICAL)
    assert any(h.doc_id in {"POL-DEV-001", "LEG-CDC-049"} for h in hits)


@pytest.mark.parametrize(("compra", "versao"), [(date(2017, 12, 20), "1.0"), (date(2018, 1, 1), "1.1")])
@pytest.mark.parametrize("method", list(Method))
def test_busca_so_devolve_a_versao_vigente_na_compra(retriever, method, compra, versao):
    hits = retriever.search("janela de devolução por desistência", day=compra, method=method, k=10)
    dev = [h for h in hits if h.doc_id == "POL-DEV-001"]
    assert dev and {h.version for h in dev} == {versao}


def test_filtro_de_intencao_mantem_transversais_e_lei(retriever):
    hits = retriever.search(
        "estorno cartão reembolso prazo",
        day=date(2018, 3, 1),
        intents=["reembolso"],
        method=Method.LEXICAL,
        k=20,
    )
    assert {h.doc_id for h in hits} <= {
        "POL-REF-001",
        "POL-SEG-001",
        "POL-SLA-002",
        "LEG-CDC-018",
        "LEG-CDC-026",
        "LEG-CDC-049",
    }
    assert "POL-REF-001" in {h.doc_id for h in hits}


def test_busca_vetorial_e_hibrida_contra_o_banco(retriever):
    for method in (Method.VECTOR, Method.HYBRID):
        hits = retriever.search("produto chegou quebrado com defeito", day=date(2018, 3, 1), method=method)
        assert hits[0].doc_id == "POL-PRD-002", method


def test_busca_por_ids_de_chunk(retriever):
    rows = retriever.repo.get_chunks(["POL-DEV-001-S03@1.1", "LEG-CDC-049"])
    assert [r.chunk_id for r in rows] == ["LEG-CDC-049", "POL-DEV-001-S03@1.1"]


AT = datetime(2018, 1, 25)


def test_escrita_em_sim_exige_posse_do_pedido(repo):
    assert repo.open_ticket("u1", OID_2, "outro", False, [], AT, None) is None  # OID_2 é do u2
    assert repo.request_cancellation("u1", OID_2, AT) is None
    assert repo.request_return("u1", OID_2, "arrependimento", None, "1.1", AT) is None
    assert repo.refund_status("u1", OID_2) is None


def test_ocorrencia_idempotente_e_encaminhamento_so_sobe(repo):
    first = repo.open_ticket("u1", OID_1, "atraso_entrega", False, ["POL-ENT-001"], AT, "cen-1")
    again = repo.open_ticket("u1", OID_1, "atraso_entrega", True, ["POL-ENT-001"], AT, "cen-1")
    later = repo.open_ticket("u1", OID_1, "atraso_entrega", False, ["POL-ENT-001"], AT, "cen-1")
    assert first == again == later
    with psycopg.connect(ADMIN) as conn:
        escalated = conn.execute(
            "SELECT escalated FROM sim.tickets WHERE ticket_id = %s", (first,)
        ).fetchone()[0]
    assert escalated is True
    assert [t.ticket_type for t in repo.customer_tickets("u1")] == ["atraso_entrega"]
    assert repo.customer_tickets("u2") == []


def test_solicitacoes_idempotentes(repo):
    assert repo.request_return(
        "u1", OID_1, "arrependimento", "LEG-CDC-049", "1.0", AT
    ) == repo.request_return("u1", OID_1, "arrependimento", "LEG-CDC-049", "1.0", AT)
    assert repo.request_cancellation("u1", OID_1, AT) == repo.request_cancellation("u1", OID_1, AT)


def test_status_do_reembolso_mais_recente(repo):
    with psycopg.connect(ADMIN) as conn:
        conn.execute(
            "INSERT INTO sim.refund_requests"
            " (order_id, amount, refund_status, requires_human_approval, requested_at) VALUES"
            " (%s, 10, 'solicitado', false, '2018-01-20'), (%s, 10, 'aprovado', false, '2018-01-22')",
            (OID_1, OID_1),
        )
    assert repo.refund_status("u1", OID_1) == "aprovado"


def test_agente_de_ponta_a_ponta_contra_o_banco(repo, retriever):
    from commerceops.agent import Agent, ChatRequest
    from tests.test_agent import ARREPENDIMENTO, ScriptedChat

    chat = ScriptedChat(ARREPENDIMENTO, "Devolução registrada, dentro da janela de 30 dias [POL-DEV-001].")
    agent = Agent(repo, retriever, load_knowledge_base(strict_legal=True), chat, KEY)
    req = ChatRequest(order_id=OID_1, zip_prefix="09790", reference_date=date(2018, 1, 25), message="desisti")
    r = agent.answer(req)
    assert r.validated and r.request_id is not None and "POL-DEV-001" in r.policy_ids
    # o contexto enviado ao LLM traz a seção da decisão na versão vigente na compra (v1.0)
    sent = json.loads(chat.calls[1][1][1]["content"])
    assert any("30 dias" in p["texto"] for p in sent["politicas"] if p["id"] == "POL-DEV-001")
    assert agent.answer(req).request_id == r.request_id  # repetir não duplica
