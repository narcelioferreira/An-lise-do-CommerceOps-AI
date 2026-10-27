"""Testa a auditoria com um mini-dataset sintético (o CI não tem os CSVs reais)."""

from pathlib import Path

import pandas as pd
import pytest

from commerceops.data.audit import FILES, load, run


def _write(d: Path, key: str, rows: list[dict], bom: bool = False) -> None:
    pd.DataFrame(rows).to_csv(d / FILES[key], index=False, encoding="utf-8-sig" if bom else "utf-8")


@pytest.fixture
def raw(tmp_path: Path) -> Path:
    def order(oid, status, purchase, carrier, customer, estimated):
        return dict(
            order_id=oid,
            customer_id=f"c{oid}",
            order_status=status,
            order_purchase_timestamp=purchase,
            order_approved_at=purchase,
            order_delivered_carrier_date=carrier,
            order_delivered_customer_date=customer,
            order_estimated_delivery_date=estimated,
        )

    _write(
        tmp_path,
        "orders",
        [
            # entregue às 14h do dia previsto: NÃO é atraso na comparação por data
            order(
                "o1", "delivered", "2018-01-01 10:00", "2018-01-03 09:00", "2018-01-10 14:00", "2018-01-10"
            ),
            # entregue 7 dias depois da previsão: atraso grave
            order(
                "o2", "delivered", "2018-01-01 10:00", "2018-01-03 09:00", "2018-01-17 08:00", "2018-01-10"
            ),
            # cancelado com data de entrega: inconsistente
            order("o3", "canceled", "2018-01-01 10:00", None, "2018-01-05 08:00", "2018-01-10"),
            order("o4", "processing", "2016-10-01 10:00", None, None, "2016-10-20"),
        ],
    )
    _write(
        tmp_path,
        "customers",
        [
            dict(
                customer_id="co1",
                customer_unique_id="u1",
                customer_zip_code_prefix=1001,
                customer_city="sp",
                customer_state="SP",
            ),
            dict(
                customer_id="co2",
                customer_unique_id="u1",
                customer_zip_code_prefix=1001,
                customer_city="sp",
                customer_state="SP",
            ),
            dict(
                customer_id="co3",
                customer_unique_id="u2",
                customer_zip_code_prefix=2002,
                customer_city="rj",
                customer_state="RJ",
            ),
            dict(
                customer_id="co4",
                customer_unique_id="u3",
                customer_zip_code_prefix=3003,
                customer_city="bh",
                customer_state="MG",
            ),
        ],
    )
    _write(
        tmp_path,
        "reviews",
        [
            # mesmo dia da entrega (00:00 < 14:00): "antes" por timestamp, não por data
            dict(
                review_id="r1",
                order_id="o1",
                review_score=5,
                review_comment_title=None,
                review_comment_message="ótimo",
                review_creation_date="2018-01-10 00:00:00",
                review_answer_timestamp="2018-01-11 10:00:00",
            ),
            # review_id repetido em outro pedido; criado de fato antes da entrega
            dict(
                review_id="r1",
                order_id="o2",
                review_score=1,
                review_comment_title="atraso",
                review_comment_message=" ",
                review_creation_date="2018-01-15 01:00:00",
                review_answer_timestamp="2018-01-16 10:00:00",
            ),
        ],
    )
    _write(
        tmp_path,
        "items",
        [
            dict(
                order_id="o1",
                order_item_id=1,
                product_id="p1",
                seller_id="s1",
                shipping_limit_date="2018-01-02 00:00",
                price=100.0,
                freight_value=10.0,
            ),
            dict(
                order_id="o2",
                order_item_id=1,
                product_id="p1",
                seller_id="s1",
                shipping_limit_date="2018-01-05 00:00",
                price=50.0,
                freight_value=5.0,
            ),
        ],
    )
    _write(
        tmp_path,
        "payments",
        [
            dict(
                order_id="o1",
                payment_sequential=1,
                payment_type="credit_card",
                payment_installments=3,
                payment_value=110.0,
            ),
            dict(
                order_id="o2",
                payment_sequential=1,
                payment_type="voucher",
                payment_installments=1,
                payment_value=20.0,
            ),
            dict(
                order_id="o2",
                payment_sequential=2,
                payment_type="boleto",
                payment_installments=1,
                payment_value=40.0,
            ),
        ],
    )
    _write(tmp_path, "products", [dict(product_id="p1", product_category_name="pc_gamer")])
    _write(
        tmp_path,
        "sellers",
        [dict(seller_id="s1", seller_zip_code_prefix=1, seller_city="sp", seller_state="SP")],
    )
    _write(
        tmp_path,
        "translation",
        [dict(product_category_name="beleza_saude", product_category_name_english="health_beauty")],
        bom=True,
    )
    return tmp_path


@pytest.fixture
def audit(raw):
    return run(load(raw))


def test_bom_detectado_e_coluna_lida_corretamente(audit):
    assert audit["files"][FILES["translation"]]["bom"] is True
    assert audit["catalog"]["categories_without_translation"] == ["pc_gamer"]


def test_geolocalizacao_opcional(audit):
    assert audit["files"][FILES["geolocation"]] == {"status": "não carregado"}


def test_atraso_por_data_nao_conta_entrega_no_dia_previsto(audit):
    d = audit["delivery"]["all"]
    assert d["late"] == 1
    assert d["late_gt_5d"] == 1


def test_avaliacao_antes_da_entrega_nas_duas_granularidades(audit):
    rt = audit["review_timing"]["before_delivery"]
    assert rt == {"by_timestamp": 2, "by_date": 1}
    # r2 tem título mas mensagem em branco: conta como "com texto"
    assert audit["review_timing"]["before_delivery_with_text"] == {"by_timestamp": 2, "by_date": 1}


def test_review_id_duplicado_em_pedidos_diferentes(audit):
    r = audit["reviews"]
    assert r["review_id_duplicated_rows"] == 1
    assert r["review_id_in_gt1_order"] == 1
    assert r["with_message"] == 1  # mensagem só com espaço não conta
    assert r["creation_time_of_day"] == {"00:00:00": 1, "01:00:00": 1}


def test_estagio_e_cliente_real(audit):
    assert audit["orders"]["stage"]["inconsistente"] == 1
    assert audit["customers"]["customer_unique_id"] == 3
    assert audit["customers"]["customers_with_gt1_order"] == 1


def test_janela_analitica_exclui_2016(audit):
    assert audit["orders"]["analytical_window"]["orders_out"] == 1


def test_despacho_apos_prazo_do_vendedor(audit):
    assert audit["delivery"]["dispatched_after_seller_limit"]["late_dispatch"] == 1


def test_pagamento_com_dois_meios(audit):
    p = audit["items_payments"]
    assert p["payments"]["orders_gt1_payment_type"] == 1
    assert p["payment_vs_items"]["paid_more"] == 1  # o2: pagou 60 por 55
