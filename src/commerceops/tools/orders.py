"""Ferramentas de consulta de pedido.

Regras de segurança (POL-SEG-001, decisão D7):
- só consulta pedido depois de verificar order_id + prefixo do CEP;
- o acesso é limitado ao customer_unique_id verificado, checado AQUI, não no prompt;
- "pedido inexistente" e "dados não conferem" são indistinguíveis para quem chama;
- order_id nunca vai cru para o trace: só o HMAC.
"""

from __future__ import annotations

import hmac
import re
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from typing import Protocol

from langfuse import get_client, observe
from pydantic import BaseModel

from commerceops.domain.orders import (
    Stage,
    days_late,
    days_since_delivery,
    is_severe_delay,
    order_stage,
)
from commerceops.observability import hash_id

ORDER_ID_RE = re.compile(r"^[0-9a-f]{32}$")
ZIP_PREFIX_RE = re.compile(r"^\d{5}$")


class OrderAccessDenied(Exception):
    """Mensagem única para pedido inexistente, CEP errado ou pedido de outro cliente."""

    def __init__(self) -> None:
        super().__init__("pedido não encontrado ou dados de verificação não conferem")


# ---------------------------------------------------------------- dados vindos do repositório


@dataclass(frozen=True)
class OrderRow:
    order_id: str
    customer_unique_id: str
    customer_zip_code_prefix: str
    order_status: str
    order_purchase_timestamp: datetime
    order_approved_at: datetime | None
    order_delivered_carrier_date: datetime | None
    order_delivered_customer_date: datetime | None
    order_estimated_delivery_date: date


@dataclass(frozen=True)
class ItemRow:
    order_item_id: int
    product_category_name: str | None
    seller_id: str
    shipping_limit_date: datetime
    price: Decimal
    freight_value: Decimal


@dataclass(frozen=True)
class PaymentRow:
    payment_sequential: int
    payment_type: str
    payment_installments: int
    payment_value: Decimal


class OrderRepository(Protocol):
    def get_order(self, order_id: str) -> OrderRow | None: ...
    def get_items(self, order_id: str) -> list[ItemRow]: ...
    def get_payments(self, order_id: str) -> list[PaymentRow]: ...
    def record_action(
        self, tool_name: str, order_id_hash: str | None, allowed: bool, reason: str
    ) -> None: ...


# ---------------------------------------------------------------- saída das ferramentas


class VerifiedCustomer(BaseModel):
    customer_unique_id: str


class ItemSummary(BaseModel):
    item: int
    category: str | None
    seller_id: str
    price: Decimal
    freight_value: Decimal


class PaymentSummary(BaseModel):
    sequential: int
    type: str
    installments: int
    value: Decimal


class OrderSummary(BaseModel):
    """Fatos do pedido já interpretados por regras determinísticas. O LLM só lê isto."""

    order_id: str
    reference_date: date
    status: str
    stage: Stage
    stage_reasons: list[str]
    purchase_date: date
    estimated_delivery_date: date
    carrier_date: date | None
    delivered_date: date | None
    days_late: int | None  # None quando o estágio não permite medir
    severe_delay: bool
    late_dispatch: bool
    days_since_delivery: int | None
    items: list[ItemSummary]
    payments: list[PaymentSummary]
    total_paid: Decimal


# ---------------------------------------------------------------- ferramentas


def _normalize_zip(zip_prefix: str) -> str:
    return re.sub(r"\D", "", zip_prefix)[:5]


@observe(name="verify_customer", as_type="tool", capture_input=False, capture_output=False)
def verify_customer(
    repo: OrderRepository, order_id: str, zip_prefix: str, *, hmac_key: str
) -> VerifiedCustomer:
    order_id = order_id.strip().lower()
    zip5 = _normalize_zip(zip_prefix)
    oid_hash = hash_id(order_id, hmac_key) if ORDER_ID_RE.fullmatch(order_id) else None

    row = repo.get_order(order_id) if oid_hash and ZIP_PREFIX_RE.fullmatch(zip5) else None
    ok = row is not None and hmac.compare_digest(row.customer_zip_code_prefix, zip5)
    repo.record_action("verify_customer", oid_hash, ok, "ok" if ok else "verificação falhou")
    if not ok:
        raise OrderAccessDenied()
    return VerifiedCustomer(customer_unique_id=row.customer_unique_id)  # type: ignore[union-attr]


@observe(name="get_order_summary", as_type="tool", capture_input=False, capture_output=False)
def get_order_summary(
    repo: OrderRepository,
    customer: VerifiedCustomer,
    order_id: str,
    reference_date: date,
    *,
    hmac_key: str,
) -> OrderSummary:
    order_id = order_id.strip().lower()
    oid_hash = hash_id(order_id, hmac_key)
    lf = get_client()
    lf.update_current_span(input={"order_id_hash": oid_hash, "reference_date": reference_date.isoformat()})

    row = repo.get_order(order_id) if ORDER_ID_RE.fullmatch(order_id) else None
    if row is None or row.customer_unique_id != customer.customer_unique_id:
        repo.record_action("get_order_summary", oid_hash, False, "pedido de outro cliente ou inexistente")
        lf.update_current_span(level="WARNING", status_message="acesso negado")
        raise OrderAccessDenied()

    items = repo.get_items(order_id)
    payments = repo.get_payments(order_id)
    st = order_stage(row.order_status, row.order_delivered_carrier_date, row.order_delivered_customer_date)

    late: int | None = None
    if st.stage in (Stage.ENTREGUE, Stage.EM_TRANSITO, Stage.PRE_ENVIO):
        late = days_late(row.order_estimated_delivery_date, row.order_delivered_customer_date, reference_date)

    limit = max((i.shipping_limit_date for i in items), default=None)
    late_dispatch = (
        st.stage is Stage.PRE_ENVIO
        and row.order_approved_at is not None
        and limit is not None
        and reference_date > limit.date()
    )

    summary = OrderSummary(
        order_id=order_id,
        reference_date=reference_date,
        status=row.order_status,
        stage=st.stage,
        stage_reasons=st.reasons,
        purchase_date=row.order_purchase_timestamp.date(),
        estimated_delivery_date=row.order_estimated_delivery_date,
        carrier_date=row.order_delivered_carrier_date.date() if row.order_delivered_carrier_date else None,
        delivered_date=row.order_delivered_customer_date.date()
        if row.order_delivered_customer_date
        else None,
        days_late=late,
        severe_delay=late is not None and is_severe_delay(late),
        late_dispatch=late_dispatch,
        days_since_delivery=(
            days_since_delivery(row.order_delivered_customer_date, reference_date)
            if st.stage is Stage.ENTREGUE and row.order_delivered_customer_date
            else None
        ),
        items=[
            ItemSummary(
                item=i.order_item_id,
                category=i.product_category_name,
                seller_id=i.seller_id,
                price=i.price,
                freight_value=i.freight_value,
            )
            for i in items
        ],
        payments=[
            PaymentSummary(
                sequential=p.payment_sequential,
                type=p.payment_type,
                installments=p.payment_installments,
                value=p.payment_value,
            )
            for p in payments
        ],
        total_paid=sum((p.payment_value for p in payments), Decimal("0")),
    )
    repo.record_action("get_order_summary", oid_hash, True, "ok")
    lf.update_current_span(
        output={
            "stage": summary.stage.value,
            "days_late": summary.days_late,
            "severe_delay": summary.severe_delay,
        }
    )
    return summary
