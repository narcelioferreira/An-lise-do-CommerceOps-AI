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


def test_hmac_do_pedido_nao_e_mascarado():
    h = hash_id("a" * 32, "chave")
    assert mask_pii(data=h) == h


def test_hmac_depende_da_chave():
    assert hash_id("a" * 32, "k1") != hash_id("a" * 32, "k2")
