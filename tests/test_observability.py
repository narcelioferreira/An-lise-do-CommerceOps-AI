from commerceops.observability import hash_id, mask_pii


def test_mascara_dados_pessoais_em_estruturas_aninhadas():
    data = {
        "msg": "pedido " + "a" * 32 + ", cep 09790-123, cpf 123.456.789-09",
        "contato": [
            "fulano@exemplo.com",
            "(11) 98765-4321",
            "+55 11 98765-4321",
            "cartão 4111 1111 1111 1111",
        ],
        "n": 3,
    }
    assert mask_pii(data=data) == {
        "msg": "pedido <id>, cep <cep>, cpf <cpf>",
        "contato": ["<email>", "<telefone>", "<telefone>", "cartão <cartao>"],
        "n": 3,
    }


def test_nao_mascara_ids_de_politica_nem_carimbos_de_data():
    # achados em traces reais: o chunk virava "<email>" e o nome da rodada, "<cartao>"
    data = {
        "chunk_id": "POL-DEV-001-S03@1.1",
        "experiment_run_name": "agente-openai_gpt-oss-20b-20261027-091345",
        "contato": "fulano@exemplo.com.br, cartão 5555555555554444",
    }
    assert mask_pii(data=data) == {
        "chunk_id": "POL-DEV-001-S03@1.1",
        "experiment_run_name": "agente-openai_gpt-oss-20b-20261027-091345",
        "contato": "<email>, cartão <cartao>",
    }


def test_hmac_do_pedido_nao_e_mascarado():
    h = hash_id("a" * 32, "chave")
    assert mask_pii(data=h) == h


def test_hmac_depende_da_chave():
    assert hash_id("a" * 32, "k1") != hash_id("a" * 32, "k2")


def test_mascara_objetos_capturados_pelo_observe():
    # regressão: o span "contextualizar" levou o OrderSummary com order_id cru para o Langfuse
    from dataclasses import dataclass

    from pydantic import BaseModel

    class Resumo(BaseModel):
        order_id: str
        total: int

    @dataclass
    class Linha:
        order_id: str

    oid = "a" * 32
    masked = mask_pii(data=["msg", Resumo(order_id=oid, total=3), Linha(order_id=oid)])
    assert masked == ["msg", {"order_id": "<id>", "total": 3}, {"order_id": "<id>"}]
