"""Regras determinísticas sobre pedidos. O LLM nunca calcula estágio, prazo ou atraso."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from enum import StrEnum

SEVERE_DELAY_DAYS = 5  # POL-ENT-003: atraso grave = mais de 5 dias corridos

PRE_SHIPMENT_STATUSES = frozenset({"created", "approved", "processing", "invoiced"})


class Stage(StrEnum):
    PRE_ENVIO = "pre_envio"
    EM_TRANSITO = "em_transito"
    ENTREGUE = "entregue"
    CANCELADO = "cancelado"
    INDISPONIVEL = "indisponivel"
    INCONSISTENTE = "inconsistente"


@dataclass(frozen=True)
class StageResult:
    stage: Stage
    reasons: list[str] = field(default_factory=list)


def _set(v: datetime | date | None) -> bool:
    return v is not None


def order_stage(
    status: str,
    carrier_date: datetime | None,
    customer_date: datetime | None,
) -> StageResult:
    """Estágio do pedido a partir do status E das datas.

    Quando status e datas se contradizem, o resultado é INCONSISTENTE e as políticas mandam
    não concluir nada e encaminhar para revisão humana (POL-ENT-002-S04).
    """
    carrier, customer = _set(carrier_date), _set(customer_date)

    if status in PRE_SHIPMENT_STATUSES:
        if carrier or customer:
            return StageResult(Stage.INCONSISTENTE, [f"status {status} com data de envio ou entrega"])
        return StageResult(Stage.PRE_ENVIO)

    if status == "shipped":
        if not carrier:
            return StageResult(Stage.INCONSISTENTE, ["shipped sem data de entrega à transportadora"])
        if customer:
            return StageResult(Stage.INCONSISTENTE, ["shipped com data de entrega ao cliente"])
        return StageResult(Stage.EM_TRANSITO)

    if status == "delivered":
        if not customer:
            return StageResult(Stage.INCONSISTENTE, ["delivered sem data de entrega ao cliente"])
        return StageResult(Stage.ENTREGUE)

    if status == "canceled":
        if customer:
            return StageResult(Stage.INCONSISTENTE, ["canceled com data de entrega ao cliente"])
        return StageResult(Stage.CANCELADO)

    if status == "unavailable":
        if carrier or customer:
            return StageResult(Stage.INCONSISTENTE, ["unavailable com data de envio ou entrega"])
        return StageResult(Stage.INDISPONIVEL)

    return StageResult(Stage.INCONSISTENTE, [f"status desconhecido: {status!r}"])


def _as_date(v: datetime | date) -> date:
    return v.date() if isinstance(v, datetime) else v


def days_late(
    estimated: datetime | date,
    delivered: datetime | date | None,
    reference: date,
) -> int:
    """Dias corridos de atraso em relação à previsão (negativo = adiantado/dentro do prazo).

    Compara por DATA, não por timestamp: a previsão do Olist é sempre meia-noite, e comparar
    timestamps faria uma entrega às 14h do dia previsto parecer atrasada.
    Se o pedido não foi entregue, mede contra a data de referência do atendimento.
    """
    end = _as_date(delivered) if delivered is not None else reference
    return (end - _as_date(estimated)).days


def is_severe_delay(late_days: int) -> bool:
    return late_days > SEVERE_DELAY_DAYS


def days_since_delivery(delivered: datetime | date, reference: date) -> int:
    """Dias corridos entre a entrega e a data de referência (base das janelas de devolução)."""
    return (reference - _as_date(delivered)).days
