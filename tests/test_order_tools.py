from datetime import date, datetime
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

from commerceops.api.main import app, get_repo
from commerceops.domain.orders import Stage
from commerceops.tools.orders import (
    ItemRow,
    OrderAccessDenied,
    OrderRow,
    PaymentRow,
    VerifiedCustomer,
    get_order_summary,
    verify_customer,
)

KEY = "chave-de-teste"
OID_A = "a" * 32  # cliente u1, CEP com zero à esquerda
OID_A2 = "c" * 32  # outro pedido do MESMO cliente u1
OID_B = "b" * 32  # cliente u2


class FakeRepo:
    def __init__(self):
        self.orders = {
            OID_A: OrderRow(
                OID_A,
                "u1",
                "09790",
                "delivered",
                datetime(2017, 12, 20, 10),
                datetime(2017, 12, 20, 11),
                datetime(2017, 12, 22, 9),
                datetime(2018, 1, 5, 18),
                date(2018, 1, 3),
            ),
            OID_A2: OrderRow(
                OID_A2,
                "u1",
                "09790",
                "processing",
                datetime(2018, 3, 1, 10),
                datetime(2018, 3, 1, 11),
                None,
                None,
                date(2018, 3, 20),
            ),
            OID_B: OrderRow(
                OID_B,
                "u2",
                "14409",
                "canceled",
                datetime(2018, 1, 1, 10),
                None,
                datetime(2018, 1, 3, 9),
                datetime(2018, 1, 9, 9),
                date(2018, 1, 20),
            ),
        }
        self.actions = []

    def get_order(self, order_id):
        return self.orders.get(order_id)

    def get_items(self, order_id):
        return [ItemRow(1, "pc_gamer", "s1", datetime(2018, 3, 5), Decimal("100.00"), Decimal("10.00"))]

    def get_payments(self, order_id):
        return [
            PaymentRow(1, "voucher", 1, Decimal("30.00")),
            PaymentRow(2, "credit_card", 3, Decimal("80.00")),
        ]

    def record_action(self, tool_name, order_id_hash, allowed, reason):
        self.actions.append((tool_name, order_id_hash, allowed, reason))

    def ping(self):
        pass


@pytest.fixture
def repo():
    return FakeRepo()


# ---------------------------------------------------------------- verificação


@pytest.mark.parametrize("zip_prefix", ["09790", "09790-123", " 09790123"])
def test_verifica_cep_com_zero_a_esquerda(repo, zip_prefix):
    assert verify_customer(repo, OID_A, zip_prefix, hmac_key=KEY).customer_unique_id == "u1"


@pytest.mark.parametrize(
    ("order_id", "zip_prefix"),
    [
        (OID_A, "9790"),  # zero à esquerda perdido (o bug do pandas)
        (OID_A, "14409"),  # CEP de outro cliente
        ("f" * 32, "09790"),  # pedido inexistente
        ("' OR 1=1 --", "09790"),  # nem chega ao banco
    ],
)
def test_verificacao_falha_com_mensagem_unica(repo, order_id, zip_prefix):
    with pytest.raises(OrderAccessDenied, match="não encontrado ou dados de verificação não conferem"):
        verify_customer(repo, order_id, zip_prefix, hmac_key=KEY)
    assert repo.actions[-1][2] is False


def test_order_id_nunca_registrado_cru(repo):
    verify_customer(repo, OID_A, "09790", hmac_key=KEY)
    _, oid_hash, _, _ = repo.actions[-1]
    assert oid_hash != OID_A and len(oid_hash) == 16


# ---------------------------------------------------------------- autorização


def test_cliente_nao_acessa_pedido_de_outro(repo):
    u1 = VerifiedCustomer(customer_unique_id="u1")
    with pytest.raises(OrderAccessDenied):
        get_order_summary(repo, u1, OID_B, date(2018, 1, 25), hmac_key=KEY)
    assert repo.actions[-1][2] is False


def test_cliente_acessa_outro_pedido_proprio(repo):
    u1 = VerifiedCustomer(customer_unique_id="u1")
    s = get_order_summary(repo, u1, OID_A2, date(2018, 3, 10), hmac_key=KEY)
    assert s.stage is Stage.PRE_ENVIO


# ---------------------------------------------------------------- fatos calculados


def test_resumo_do_caso_limite_de_devolucao(repo):
    u1 = VerifiedCustomer(customer_unique_id="u1")
    s = get_order_summary(repo, u1, OID_A, date(2018, 1, 25), hmac_key=KEY)
    assert s.stage is Stage.ENTREGUE
    assert s.purchase_date == date(2017, 12, 20)  # define a versão da POL-DEV-001
    assert s.days_since_delivery == 20
    assert s.days_late == 2 and not s.severe_delay
    assert s.total_paid == Decimal("110.00")
    assert [p.type for p in s.payments] == ["voucher", "credit_card"]


def test_despacho_atrasado(repo):
    u1 = VerifiedCustomer(customer_unique_id="u1")
    assert get_order_summary(repo, u1, OID_A2, date(2018, 3, 10), hmac_key=KEY).late_dispatch is True
    assert get_order_summary(repo, u1, OID_A2, date(2018, 3, 5), hmac_key=KEY).late_dispatch is False


# ---------------------------------------------------------------- API


@pytest.fixture
def client(repo):
    app.dependency_overrides[get_repo] = lambda: repo
    with TestClient(app) as c:
        app.state.repo = repo
        yield c
    app.dependency_overrides.clear()


def test_api_consulta_pedido(client):
    r = client.post(
        "/v1/orders/lookup", json={"order_id": OID_A, "zip_prefix": "09790", "reference_date": "2018-01-25"}
    )
    assert r.status_code == 200
    assert r.json()["stage"] == "entregue"


def test_api_nao_revela_se_pedido_existe(client):
    body = {"zip_prefix": "00000", "reference_date": "2018-01-25"}
    existe = client.post("/v1/orders/lookup", json=body | {"order_id": OID_A})
    nao_existe = client.post("/v1/orders/lookup", json=body | {"order_id": "f" * 32})
    assert existe.status_code == nao_existe.status_code == 404
    assert existe.json() == nao_existe.json()


def test_health(client):
    assert client.get("/health/live").json() == {"status": "ok"}
    assert client.get("/health/ready").status_code == 200
    deep = client.get("/health/deep").json()
    assert deep["checks"]["llm"] == "não configurado"
    assert deep["checks"]["langfuse"] == "desligado"
