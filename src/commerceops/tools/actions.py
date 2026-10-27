"""Executa a `Decision` no schema `sim`: ocorrência, cancelamento e devolução.

Só o código chama estas funções, nunca o LLM. O repositório confere a posse do pedido no próprio
SQL, então mesmo uma chamada errada não grava nada em pedido de outro cliente (OWASP ASI02/ASI03).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, time
from typing import Protocol

from commerceops.domain.decisions import Decision, TicketRow
from commerceops.observability import hash_id
from commerceops.tools.orders import OrderAccessDenied, OrderSummary, VerifiedCustomer


class ActionRepository(Protocol):
    def open_ticket(
        self,
        customer_unique_id: str,
        order_id: str,
        ticket_type: str,
        escalated: bool,
        policy_ids: list[str],
        opened_at: datetime,
        scenario_id: str | None,
    ) -> int | None: ...
    def request_cancellation(
        self, customer_unique_id: str, order_id: str, requested_at: datetime
    ) -> int | None: ...
    def request_return(
        self,
        customer_unique_id: str,
        order_id: str,
        reason: str | None,
        legal_basis: str | None,
        policy_version: str | None,
        requested_at: datetime,
    ) -> int | None: ...
    def refund_status(self, customer_unique_id: str, order_id: str) -> str | None: ...
    def customer_tickets(self, customer_unique_id: str) -> list[TicketRow]: ...
    def record_action(
        self, tool_name: str, order_id_hash: str | None, allowed: bool, reason: str
    ) -> None: ...


@dataclass(frozen=True)
class Outcome:
    ticket_id: int | None = None
    request_id: int | None = None


def execute(
    repo: ActionRepository,
    customer: VerifiedCustomer,
    summary: OrderSummary,
    decision: Decision,
    *,
    hmac_key: str,
    scenario_id: str | None = None,
) -> Outcome:
    # "Hoje" é a data de referência do cenário, nunca o relógio (decisão D4)
    at = datetime.combine(summary.reference_date, time())
    cid, oid = customer.customer_unique_id, summary.order_id
    ticket_id = request_id = None

    if decision.ticket_type:
        ticket_id = repo.open_ticket(
            cid, oid, decision.ticket_type, decision.escalate, decision.policy_ids, at, scenario_id
        )
        _audit(repo, "open_ticket", oid, ticket_id, hmac_key)
    if decision.request == "cancelamento":
        request_id = repo.request_cancellation(cid, oid, at)
        _audit(repo, "request_cancellation", oid, request_id, hmac_key)
    elif decision.request == "devolucao":
        # Devolução sempre traz a versão da política; se faltar, o NOT NULL do banco recusa
        request_id = repo.request_return(
            cid, oid, decision.return_reason, decision.legal_basis, decision.policy_version, at
        )
        _audit(repo, "request_return", oid, request_id, hmac_key)
    return Outcome(ticket_id, request_id)


def _audit(repo: ActionRepository, tool: str, order_id: str, written_id: int | None, hmac_key: str) -> None:
    repo.record_action(
        tool, hash_id(order_id, hmac_key), written_id is not None, "ok" if written_id else "sem posse"
    )
    if written_id is None:
        raise OrderAccessDenied()
