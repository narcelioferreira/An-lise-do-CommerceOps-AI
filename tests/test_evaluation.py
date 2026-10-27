import pytest

from commerceops.agent import ChatResult
from commerceops.evaluation import load_scenarios, retrieval_score, score, summarize
from tests.test_decisions import KB

SCENARIOS = load_scenarios()
CHUNK_IDS = {c.chunk_id for c in KB.chunks()}
TICKET_TYPES = {
    "atraso_entrega", "expedicao_atrasada", "investigacao_entrega", "divergencia_produto",
    "defeito_produto", "cobranca", "reclamacao_atendimento", "outro",
}  # fmt: skip


def result(**kw) -> ChatResult:
    base = dict(
        answer="ok",
        intent="arrependimento",
        sentiment="neutro",
        confidence=0.9,
        escalated=False,
        policy_ids=["POL-DEV-001"],
        ticket_id=None,
        request_id=1,
        actions=["devolucao"],
        validated=True,
    )
    return ChatResult(**(base | kw))


# ---------------------------------------------------------------- gabarito


def test_cenarios_simulados_e_unicos():
    assert len(SCENARIOS) >= 20 and all(s.simulated for s in SCENARIOS)


@pytest.mark.parametrize("s", SCENARIOS, ids=lambda s: s.scenario_id)
def test_gabarito_so_usa_ids_existentes(s):
    assert s.access_denied or s.expected_intent in KB.taxonomy.intent_ids
    assert set(s.expected_chunk_ids) <= CHUNK_IDS
    assert set(s.expected_policy_ids) <= set(KB.policies) | KB.legal_ids
    for a in s.expected_actions:
        assert a in ("devolucao", "cancelamento") or a.removeprefix("ocorrencia:") in TICKET_TYPES
    assert not s.must_escalate or any(a.startswith("ocorrencia:") for a in s.expected_actions)


# Casos-limite obrigatórios de docs/01_politicas_v1.1.md, seção 4
@pytest.mark.parametrize(
    "prefix",
    [
        "DEV-001-caso-limite",
        "DEV-001-quinto-dia",
        "DEV-001-apos-janela",
        "ENT-002-inconsistente",
        "SEG-001-cep-de-outro",
        "REF-001-voucher-e-cartao",
        "SEG-001-injecao",
    ],
)
def test_cobre_os_casos_limite_obrigatorios(prefix):
    assert any(s.scenario_id.startswith(prefix) for s in SCENARIOS)


# ---------------------------------------------------------------- métricas


def test_score_cenario_correto():
    s = next(x for x in SCENARIOS if x.scenario_id == "DEV-001-caso-limite-versao-01")
    assert set(score(s, result()).values()) == {1.0}


def test_score_penaliza_frase_proibida_e_acao_errada():
    s = next(x for x in SCENARIOS if x.scenario_id == "DEV-001-caso-limite-versao-01")
    r = score(s, result(answer="Prazo de 15 dias.", actions=[], policy_ids=[]))
    assert r["sem_frase_proibida"] == r["acoes_corretas"] == r["politicas_recall"] == 0.0


def test_score_acesso_negado():
    s = next(x for x in SCENARIOS if x.access_denied)
    assert score(s, None) == {"acesso_negado_correto": 1.0}
    assert score(s, result()) == {"acesso_negado_correto": 0.0}


def test_metricas_de_busca():
    assert retrieval_score(["x", "a", "b"], ["a", "c"], k=5) == {"recall@5": 0.5, "mrr@5": 0.5}
    assert retrieval_score(["x", "y", "a"], ["a"], k=2) == {"recall@2": 0.0, "mrr@2": 0.0}


def test_resumo_conta_so_onde_a_metrica_se_aplica():
    assert summarize([{"a": 1.0, "b": 0.0}, {"a": 0.0}]) == {
        "a": {"media": 0.5, "n": 2},
        "b": {"media": 0.0, "n": 1},
    }
