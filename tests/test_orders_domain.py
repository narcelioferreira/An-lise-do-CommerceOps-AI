from datetime import date, datetime

import pytest

from commerceops.domain.orders import (
    Stage,
    days_late,
    days_since_delivery,
    is_severe_delay,
    order_stage,
)

T = datetime(2018, 1, 10, 14, 0)


@pytest.mark.parametrize(
    ("status", "carrier", "customer", "expected"),
    [
        ("created", None, None, Stage.PRE_ENVIO),
        ("approved", None, None, Stage.PRE_ENVIO),
        ("processing", None, None, Stage.PRE_ENVIO),
        ("invoiced", None, None, Stage.PRE_ENVIO),
        ("shipped", T, None, Stage.EM_TRANSITO),
        ("delivered", T, T, Stage.ENTREGUE),
        ("delivered", None, T, Stage.ENTREGUE),  # 2 casos reais: entregue sem data de despacho
        ("canceled", None, None, Stage.CANCELADO),
        ("canceled", T, None, Stage.CANCELADO),  # cancelado após despacho: possível
        ("unavailable", None, None, Stage.INDISPONIVEL),
        # contradições observadas na auditoria
        ("canceled", T, T, Stage.INCONSISTENTE),
        ("delivered", T, None, Stage.INCONSISTENTE),
        ("approved", T, None, Stage.INCONSISTENTE),
        ("shipped", None, None, Stage.INCONSISTENTE),
        ("unavailable", T, None, Stage.INCONSISTENTE),
        ("algo_novo", None, None, Stage.INCONSISTENTE),
    ],
)
def test_order_stage(status, carrier, customer, expected):
    result = order_stage(status, carrier, customer)
    assert result.stage is expected
    assert bool(result.reasons) == (expected is Stage.INCONSISTENTE)


def test_entrega_no_dia_previsto_nao_e_atraso():
    # previsão do Olist é sempre meia-noite; entrega às 14h do mesmo dia está no prazo
    assert days_late(datetime(2018, 1, 10), datetime(2018, 1, 10, 14), date(2018, 3, 1)) == 0


def test_pedido_nao_entregue_mede_contra_data_de_referencia():
    assert days_late(datetime(2018, 1, 10), None, date(2018, 1, 8)) == -2
    assert days_late(datetime(2018, 1, 10), None, date(2018, 1, 16)) == 6


@pytest.mark.parametrize(("dias", "grave"), [(5, False), (6, True), (0, False), (-3, False)])
def test_limite_do_atraso_grave(dias, grave):
    assert is_severe_delay(dias) is grave


def test_dias_desde_a_entrega():
    assert days_since_delivery(datetime(2018, 1, 5, 18), date(2018, 1, 25)) == 20
