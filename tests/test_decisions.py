import re
from datetime import date, datetime
from decimal import Decimal

import pytest

from commerceops.domain.decisions import Signal, TicketRow, decide, detect_signals
from commerceops.domain.orders import Stage
from commerceops.knowledge.loader import load_knowledge_base
from commerceops.tools.orders import ItemSummary, OrderSummary, PaymentSummary

KB = load_knowledge_base()


def summary(stage: Stage, **kw) -> OrderSummary:
    base = dict(
        order_id="a" * 32,
        reference_date=date(2018, 3, 1),
        status="x",
        stage=stage,
        stage_reasons=[],
        purchase_date=date(2018, 2, 1),
        estimated_delivery_date=date(2018, 2, 20),
        carrier_date=None,
        delivered_date=None,
        days_late=None,
        severe_delay=False,
        late_dispatch=False,
        days_since_delivery=None,
        items=[
            ItemSummary(item=1, category="x", seller_id="s1", price=Decimal(90), freight_value=Decimal(10))
        ],
        payments=[PaymentSummary(sequential=1, type="credit_card", installments=1, value=Decimal(100))],
        total_paid=Decimal(100),
    )
    return OrderSummary(**(base | kw))


def delivered(days_ago: int, purchase=date(2018, 2, 1), ref=date(2018, 3, 1), **kw) -> OrderSummary:
    return summary(
        Stage.ENTREGUE,
        purchase_date=purchase,
        reference_date=ref,
        delivered_date=date.fromordinal(ref.toordinal() - days_ago),
        days_since_delivery=days_ago,
        days_late=0,
        **kw,
    )


# ---------------------------------------------------------------- entrega (POL-ENT-001/002/003)


def test_dentro_do_prazo_so_informa():
    d = decide("consultar_prazo", summary(Stage.EM_TRANSITO, days_late=-3), KB)
    assert "POL-ENT-001-S02@1.0" in d.sections
    assert (d.ticket_type, d.escalate) == (None, False)


def test_prazo_vencido_abre_ocorrencia_sem_encaminhar():
    d = decide("entrega_atrasada", summary(Stage.EM_TRANSITO, days_late=3), KB)
    assert "POL-ENT-001-S03@1.0" in d.sections
    assert (d.ticket_type, d.escalate) == ("atraso_entrega", False)


def test_atraso_grave_encaminha_sem_valores():
    d = decide("entrega_atrasada", summary(Stage.EM_TRANSITO, days_late=6, severe_delay=True), KB)
    assert {"POL-ENT-003-S02@1.0", "POL-SLA-002-S02@1.0"} <= set(d.sections)
    assert d.escalate and d.ticket_type == "atraso_entrega"


def test_entregue_mas_nao_recebido_investiga_e_encaminha():
    d = decide("pedido_nao_recebido", delivered(3), KB)
    assert "POL-ENT-002-S02@1.0" in d.sections and "POL-ENT-001-S01@1.0" not in d.sections
    assert d.escalate and d.ticket_type == "investigacao_entrega"


def test_nao_despachado_apos_prazo_de_postagem():
    d = decide("consultar_prazo", summary(Stage.PRE_ENVIO, days_late=-5, late_dispatch=True), KB)
    assert "POL-ENT-001-S04@1.0" in d.sections
    assert d.ticket_type == "expedicao_atrasada"


@pytest.mark.parametrize("intent", ["consultar_prazo", "cancelar_pedido", "arrependimento", "reembolso"])
def test_pedido_inconsistente_nunca_conclui(intent):
    d = decide(intent, summary(Stage.INCONSISTENTE), KB)
    assert d.sections[0] == "POL-ENT-002-S04@1.0"
    assert d.escalate and d.request is None


# ---------------------------------------------------------------- devolução (POL-DEV-001, LEG-CDC-049)


def test_caso_limite_compra_em_2017_usa_janela_de_30_dias():
    s = delivered(20, purchase=date(2017, 12, 20), ref=date(2018, 1, 25))
    d = decide("arrependimento", s, KB)
    assert "POL-DEV-001-S02@1.0" in d.sections
    assert (d.request, d.policy_version, d.escalate) == ("devolucao", "1.0", False)


def test_mesmo_prazo_com_compra_em_2018_vai_para_humano_sem_negar():
    d = decide("arrependimento", delivered(20, purchase=date(2018, 1, 2)), KB)
    assert "POL-DEV-001-S02@1.1" in d.sections
    assert d.escalate and d.request is None


def test_dentro_de_7_dias_cita_a_lei():
    d = decide("arrependimento", delivered(5), KB)
    assert "LEG-CDC-049" in d.sections
    assert (d.request, d.legal_basis) == ("devolucao", "LEG-CDC-049")


def test_devolucao_de_valor_alto_exige_aprovacao_humana():
    d = decide("arrependimento", delivered(5, total_paid=Decimal("1500.00")), KB)
    assert d.request == "devolucao" and d.escalate
    assert "POL-REF-001-S03@1.0" in d.sections


def test_devolucao_sem_motivo_pergunta_antes():
    d = decide("devolver_produto", delivered(5), KB)
    assert d.sections == ("POL-DEV-001-S04@1.1",)
    assert (d.request, d.ticket_type, d.escalate) == (None, None, False)


# ---------------------------------------------------------------- cancelamento (POL-CAN-001)


def test_cancelamento_antes_do_envio_registra_solicitacao():
    d = decide("cancelar_pedido", summary(Stage.PRE_ENVIO, days_late=-5), KB)
    assert d.request == "cancelamento" and "POL-CAN-001-S02@1.0" in d.sections


def test_cancelamento_em_transito_nao_registra():
    d = decide("cancelar_pedido", summary(Stage.EM_TRANSITO, days_late=-5), KB)
    assert d.request is None and "POL-DEV-001-S01@1.1" in d.sections


def test_cancelamento_de_pedido_entregue_vira_devolucao():
    assert decide("cancelar_pedido", delivered(3), KB).request == "devolucao"


# ---------------------------------------------------------------- produto, financeiro, atendimento


def test_defeito_com_risco_a_saude_encaminha_e_orienta_parar_uso():
    s = delivered(10)
    d = decide("produto_com_defeito", s, KB, signals=detect_signals("o carregador esquentou e deu choque"))
    assert {"POL-PRD-002-S04@1.0", "LEG-CDC-026"} <= set(d.sections)
    assert d.escalate and d.ticket_type == "defeito_produto"


def test_produto_errado_com_dois_vendedores():
    items = [
        ItemSummary(item=i, category="x", seller_id=f"s{i}", price=Decimal(50), freight_value=Decimal(0))
        for i in (1, 2)
    ]
    d = decide("pedido_incompleto", delivered(2, items=items), KB)
    assert "POL-PRD-001-S02@1.0" in d.sections and d.ticket_type == "divergencia_produto"


@pytest.mark.parametrize(("status", "frase"), [(None, "Não há solicitação"), ("aprovado", "aprovado")])
def test_reembolso_informa_exatamente_o_status(status, frase):
    d = decide("reembolso", delivered(3), KB, refund_status=status)
    assert any(frase in n for n in d.notes) and not d.escalate


def test_cobranca_com_valor_diferente_encaminha():
    d = decide("cobranca_pagamento", delivered(3), KB, signals=detect_signals("me cobraram a mais"))
    assert "POL-PAG-001-S02@1.0" in d.sections and d.escalate and d.ticket_type == "cobranca"


def test_reclamacao_com_ocorrencia_vencida_encaminha():
    tickets = [TicketRow("atraso_entrega", "aberto", datetime(2018, 2, 20))]
    d = decide("reclamar_do_atendimento", delivered(3), KB, tickets=tickets)
    assert d.escalate and d.ticket_type == "reclamacao_atendimento"
    ok = decide(
        "reclamar_do_atendimento", delivered(3), KB, tickets=[TicketRow("x", "aberto", datetime(2018, 2, 28))]
    )
    assert not ok.escalate


# ---------------------------------------------------------------- sinais e monotonicidade


@pytest.mark.parametrize(
    ("texto", "sinais"),
    [
        ("vou no Procon", {Signal.JURIDICO}),
        ("meu pedido está em processamento?", set()),  # "process" sozinho não é sinal jurídico
        ("preferi outro modelo", set()),  # "feri" dentro de palavra não é ferimento
        ("não reconheço essa cobrança", {Signal.COBRANCA_NAO_RECONHECIDA}),
        ("o produto pegou fogo, vou processar", {Signal.RISCO_SAUDE, Signal.JURIDICO}),
    ],
)
def test_deteccao_de_sinais(texto, sinais):
    assert detect_signals(texto) == sinais


INTENTS = [i.id for i in KB.taxonomy.intents]
CASES = [summary(Stage.EM_TRANSITO, days_late=-2), delivered(3), summary(Stage.PRE_ENVIO, days_late=-5)]


@pytest.mark.parametrize("intent", INTENTS)
@pytest.mark.parametrize("signal", list(Signal))
def test_sinal_nunca_reduz_encaminhamento(intent, signal):
    for s in CASES:
        assert decide(intent, s, KB, signals={signal}).escalate >= decide(intent, s, KB).escalate


@pytest.mark.parametrize("intent", INTENTS)
def test_toda_secao_citada_existe_na_base(intent):
    ids = {c.chunk_id for c in KB.chunks()}
    for s in CASES:
        assert set(decide(intent, s, KB).sections) <= ids


@pytest.mark.parametrize("intent", INTENTS)
def test_encaminhamento_sempre_tem_ocorrencia(intent):
    for s in [*CASES, summary(Stage.INCONSISTENTE)]:
        d = decide(intent, s, KB, signals={Signal.JURIDICO})
        assert d.escalate and d.ticket_type


@pytest.mark.parametrize("intent", INTENTS)
def test_politica_mencionada_em_nota_esta_entre_as_citadas(intent):
    # O LLM repete as notas; citar política fora das seções faz o validador recusar a resposta
    late = summary(Stage.PRE_ENVIO, days_late=-5, late_dispatch=True)
    for s in [*CASES, late, summary(Stage.EM_TRANSITO, days_late=8, severe_delay=True)]:
        d = decide(intent, s, KB, signals=set(Signal))
        mentioned = set(re.findall(r"(?:POL-[A-Z]{3}-\d{3}|LEG-CDC-\d{3})", " ".join(d.notes)))
        assert mentioned <= set(d.policy_ids), (intent, mentioned - set(d.policy_ids))
