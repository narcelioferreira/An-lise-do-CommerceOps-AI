import shutil
from datetime import date
from pathlib import Path

import pytest
import yaml

from commerceops.knowledge.loader import (
    DEFAULT_KB_DIR,
    KnowledgeBaseError,
    load_knowledge_base,
)


@pytest.fixture(scope="module")
def kb():
    return load_knowledge_base()


@pytest.fixture
def kb_copy(tmp_path: Path) -> Path:
    dst = tmp_path / "kb"
    shutil.copytree(DEFAULT_KB_DIR, dst)
    return dst


def _edit(path: Path, fn) -> None:
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    fn(data)
    path.write_text(yaml.safe_dump(data, allow_unicode=True, sort_keys=False), encoding="utf-8")


def test_base_real_e_coerente(kb):
    assert len(kb.policies) == 12
    assert {"LEG-CDC-018", "LEG-CDC-026", "LEG-CDC-049"} == kb.legal_ids


def test_toda_intencao_acionavel_tem_politica(kb):
    sem_politica = {i.id for i in kb.taxonomy.intents if not i.policies}
    assert sem_politica == {"elogio_ou_satisfacao", "outro_ou_ambiguo"}


def test_chunk_ids_unicos(kb):
    ids = [c.chunk_id for c in kb.chunks()]
    assert len(ids) == len(set(ids))


def test_texto_legal_nunca_marcado_como_ficticio(kb):
    for c in kb.chunks():
        assert c.fictional is (c.source_type == "fictional_policy")


@pytest.mark.parametrize(
    ("compra", "versao", "janela"),
    [
        (date(2017, 12, 20), "1.0", "30 dias"),  # caso-limite: compra em 2017, solicitação em 2018
        (date(2017, 12, 31), "1.0", "30 dias"),
        (date(2018, 1, 1), "1.1", "15 dias"),
    ],
)
def test_versao_da_devolucao_segue_data_da_compra(kb, compra, versao, janela):
    v = kb.policies["POL-DEV-001"].version_on(compra)
    assert v.version == versao
    s02 = next(s for s in v.sections if s.section_id == "POL-DEV-001-S02")
    assert janela in s02.text


def test_janela_operacional_nunca_menor_que_prazo_legal_e_igual_ao_texto(kb):
    for v in kb.policies["POL-DEV-001"].versions:
        dias = v.params["return_window_days"]
        s02 = next(s for s in v.sections if s.section_id == "POL-DEV-001-S02")
        assert dias >= 7
        assert f"em até {dias} dias corridos" in s02.text


# --- A validação precisa pegar os erros que existiam na v1.0 do pacote -----------------


def test_detecta_intencao_fora_da_taxonomia(kb_copy):
    _edit(kb_copy / "policies/POL-ENT-002.yaml", lambda d: d["intents"].append("extravio"))
    with pytest.raises(KnowledgeBaseError, match="fora da taxonomia: extravio"):
        load_knowledge_base(kb_copy)


def test_detecta_referencia_a_politica_inexistente(kb_copy):
    def fn(d):
        d["versions"][0]["sections"][0]["text"] += " Ver POL-ENT-009."

    _edit(kb_copy / "policies/POL-ENT-001.yaml", fn)
    with pytest.raises(KnowledgeBaseError, match="POL-ENT-009"):
        load_knowledge_base(kb_copy)


def test_detecta_mapeamento_unilateral(kb_copy):
    def fn(d):
        d["intents"][0]["policies"].append("POL-PAG-001")

    _edit(kb_copy / "intents.yaml", fn)
    with pytest.raises(KnowledgeBaseError, match="POL-PAG-001 não lista a intenção consultar_prazo"):
        load_knowledge_base(kb_copy)


def test_detecta_vigencias_sobrepostas(kb_copy):
    _edit(
        kb_copy / "policies/POL-DEV-001.yaml",
        lambda d: d["versions"][0].update(effective_until="2018-06-30"),
    )
    with pytest.raises(ValueError, match="se sobrepõem"):
        load_knowledge_base(kb_copy)


def test_detecta_campo_inexistente_no_dataset(kb_copy):
    def fn(d):
        d["versions"][0]["sections"][0]["requires_order_data"].append("tracking_code")

    _edit(kb_copy / "policies/POL-ENT-001.yaml", fn)
    with pytest.raises(ValueError, match="tracking_code"):
        load_knowledge_base(kb_copy)


def test_textos_legais_conferidos_com_a_fonte_oficial():
    assert load_knowledge_base(strict_legal=True).legal_ids == {"LEG-CDC-018", "LEG-CDC-026", "LEG-CDC-049"}


def test_modo_estrito_recusa_texto_legal_nao_verificado(kb_copy):
    def fn(d):
        d["articles"][0].update(verification_status="pendente", verified_at=None)

    _edit(kb_copy / "legal/cdc.yaml", fn)
    with pytest.raises(KnowledgeBaseError, match="LEG-CDC-018: texto legal ainda não verificado"):
        load_knowledge_base(kb_copy, strict_legal=True)


def test_recusa_tag_yaml_executavel(kb_copy):
    # OWASP AST04: o carregador usa safe_load; tag de objeto Python não pode ser construída
    path = kb_copy / "policies/POL-CAN-001.yaml"
    path.write_text("policy_id: !!python/object/apply:os.getcwd []\n", encoding="utf-8")
    with pytest.raises(yaml.constructor.ConstructorError):
        load_knowledge_base(kb_copy)


def test_recusa_campo_desconhecido_no_yaml(kb_copy):
    _edit(kb_copy / "policies/POL-CAN-001.yaml", lambda d: d.update(executar="rm -rf /"))
    with pytest.raises(ValueError, match="executar"):
        load_knowledge_base(kb_copy)
