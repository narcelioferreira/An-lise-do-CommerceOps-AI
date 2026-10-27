"""Decisão de atendimento em código: intenção + fatos do pedido -> seções aplicáveis e ação.

O LLM nunca decide. Ele recebe a `Decision` pronta e só a redige para o cliente. Regras gerais:
- toda seção citada é resolvida na versão vigente na data da compra (decisão D3);
- encaminhamento é monotônico: qualquer sinal encaminha e nada desfaz um encaminhamento;
- nada é negado automaticamente: fora das regras, o caso vai para revisão humana (POL-SLA-002).
"""

from __future__ import annotations

import re
from collections.abc import Set
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal
from enum import StrEnum

from commerceops.domain.orders import Stage
from commerceops.knowledge.loader import KnowledgeBase
from commerceops.tools.orders import OrderSummary

LEGAL_RETURN_DAYS = 7  # LEG-CDC-049
HIGH_VALUE = Decimal("1000.00")  # POL-REF-001-S03 e decisão D8
TICKET_UPDATE_DAYS = {"cancelamento": 1}  # POL-SLA-001-S01; demais ocorrências: 3 dias
DEFAULT_UPDATE_DAYS = 3


class Signal(StrEnum):
    """Gatilhos de encaminhamento da POL-SLA-002 que dependem do texto do cliente."""

    RISCO_SAUDE = "risco_saude_seguranca"
    JURIDICO = "orgao_defesa_ou_juridico"
    COBRANCA_NAO_RECONHECIDA = "cobranca_nao_reconhecida"
    VALOR_DIFERENTE = "valor_diferente"


_SIGNAL_PATTERNS = {
    Signal.RISCO_SAUDE: (
        r"choque|superaquec|aqueceu|esquent(?:ou|ando)|pegou fogo|fumaça|\bqueim(?:ou|ad[oa]|adura)"
        r"|\bferi(?:u|d[oa]|mento)|machuc|vazament|intoxic|estragad"
    ),
    Signal.JURIDICO: r"procon|advogad|\bprocess(?:o|ar|arei)\b|justiça|judicial|reclame aqui|consumidor\.gov",
    Signal.COBRANCA_NAO_RECONHECIDA: r"não reconheço|nao reconheco|fraude|clonad|chargeback|contesta",
    Signal.VALOR_DIFERENTE: r"cobra(?:ram|do)? a mais|valor (?:errado|diferente)|cobrança (?:errad|duplicad)",
}


def detect_signals(message: str) -> set[Signal]:
    """Detecção por regra, somada (nunca substituída) aos sinais que o classificador apontar."""
    text = message.lower()
    return {s for s, pattern in _SIGNAL_PATTERNS.items() if re.search(pattern, text)}


@dataclass(frozen=True)
class TicketRow:
    ticket_type: str
    ticket_status: str
    ticket_opened_at: datetime


@dataclass(frozen=True)
class Decision:
    sections: tuple[str, ...]  # chunk_ids que fundamentam a resposta
    notes: tuple[str, ...]  # fatos que a resposta precisa transmitir, já calculados
    escalate: bool = False
    ticket_type: str | None = None
    request: str | None = None  # "cancelamento" ou "devolucao"
    return_reason: str | None = None
    legal_basis: str | None = None
    policy_version: str | None = None

    @property
    def policy_ids(self) -> list[str]:
        return sorted({s.split("@")[0][:11] for s in self.sections})


@dataclass
class _Builder:
    kb: KnowledgeBase
    purchase: date
    sections: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    escalate: bool = False
    ticket_type: str | None = None
    request: str | None = None
    return_reason: str | None = None
    legal_basis: str | None = None
    policy_version: str | None = None

    def version(self, policy_id: str) -> str:
        v = self.kb.policies[policy_id].version_on(self.purchase)
        if v is None:
            raise ValueError(f"{policy_id} sem versão vigente em {self.purchase}")
        return v.version

    def cite(self, policy_id: str, *sections: int) -> _Builder:
        v = self.version(policy_id)
        self.sections += [
            f"{policy_id}-S{n:02d}@{v}" for n in sections if f"{policy_id}-S{n:02d}@{v}" not in self.sections
        ]
        return self

    def law(self, legal_id: str) -> _Builder:
        if legal_id not in self.sections:
            self.sections.append(legal_id)
        return self

    def note(self, text: str) -> _Builder:
        self.notes.append(text)
        return self

    def ticket(self, ticket_type: str, *, escalate: bool = False) -> _Builder:
        self.ticket_type = self.ticket_type or ticket_type
        self.escalate = self.escalate or escalate
        return self

    def to_human(self) -> _Builder:
        self.escalate = True
        return self.cite("POL-SLA-002", 1, 2)

    def build(self) -> Decision:
        if self.escalate:
            self.to_human()
            self.ticket_type = self.ticket_type or "outro"
            self.note("O caso foi encaminhado para análise de uma pessoa da equipe; não prometer resultado.")
        return Decision(
            tuple(self.sections),
            tuple(self.notes),
            self.escalate,
            self.ticket_type,
            self.request,
            self.return_reason,
            self.legal_basis,
            self.policy_version,
        )


def _fmt(d: date) -> str:
    return d.strftime("%d/%m/%Y")


# ---------------------------------------------------------------- regras por assunto


def _delivery(b: _Builder, s: OrderSummary, intent: str) -> None:
    """POL-ENT-001/002/003 para pedidos que não estão inconsistentes."""
    if s.stage in (Stage.CANCELADO, Stage.INDISPONIVEL):
        b.cite("POL-CAN-001", 1).note(f"O pedido consta como {s.stage.value}.")
        return
    if s.stage is Stage.ENTREGUE:
        if intent == "pedido_nao_recebido":
            b.cite("POL-ENT-002", 2, 3).ticket("investigacao_entrega", escalate=True)
            b.note(f"O pedido consta como entregue em {_fmt(s.delivered_date)}; não contestar o cliente.")
            b.note("Foi aberta investigação de entrega, com retorno inicial em até 3 dias corridos.")
            return
        b.cite("POL-ENT-001", 1).note(f"O pedido foi entregue em {_fmt(s.delivered_date)}.")
        if intent == "entrega_atrasada" and s.severe_delay:
            b.cite("POL-ENT-003", 1, 2).ticket("atraso_entrega", escalate=True)
            b.note(f"A entrega ocorreu {s.days_late} dias corridos após a previsão; não mencionar valores.")
        return

    # pre_envio ou em_transito
    if intent == "pedido_nao_recebido":
        b.cite("POL-ENT-002", 1)
    b.cite("POL-ENT-001", 1, 5)
    estimated = _fmt(s.estimated_delivery_date)
    if s.late_dispatch:
        b.cite("POL-ENT-001", 4).cite("POL-CAN-001", 1).ticket("expedicao_atrasada")
        b.note("O pedido ainda não foi despachado e passou do prazo de postagem; ocorrência aberta.")
        b.note("O cliente pode pedir o cancelamento (POL-CAN-001).")
    elif s.days_late is not None and s.days_late <= 0:
        b.cite("POL-ENT-001", 2).note(f"O pedido está dentro do prazo; previsão de entrega em {estimated}.")
        return
    if s.days_late is not None and s.days_late > 0:
        b.cite("POL-ENT-001", 3).ticket("atraso_entrega")
        b.note(
            f"A previsão ({estimated}) venceu há {s.days_late} dias corridos; ocorrência de atraso aberta."
        )
        b.note("Retorno da verificação logística em até 3 dias corridos.")
        if s.severe_delay:
            b.cite("POL-ENT-003", 1, 2).to_human()


def _cancel(b: _Builder, s: OrderSummary) -> None:
    b.cite("POL-CAN-001", 1)
    if s.stage is Stage.PRE_ENVIO:
        b.cite("POL-CAN-001", 2)
        b.request = "cancelamento"
        b.note("Solicitação de cancelamento registrada com status solicitado; retorno em até 1 dia corrido.")
        b.note("Não confirmar o cancelamento como concluído.")
    elif s.stage is Stage.EM_TRANSITO:
        b.cite("POL-DEV-001", 1).note(
            "O pedido já foi despachado e não pode ser cancelado; o cliente pode recusar a entrega ou "
            "devolver após o recebimento."
        )
    elif s.stage is Stage.ENTREGUE:
        _return(b, s)
    else:
        b.cite("POL-REF-001", 1).note(f"O pedido já consta como {s.stage.value}.")


def _return(b: _Builder, s: OrderSummary) -> None:
    """POL-DEV-001 por desistência: três faixas, nunca negar."""
    if s.stage is not Stage.ENTREGUE:
        _cancel(b, s)
        return
    v = b.kb.policies["POL-DEV-001"].version_on(b.purchase)
    window = v.params["return_window_days"]
    days = s.days_since_delivery
    b.cite("POL-DEV-001", 1, 3)
    if days is not None and days <= LEGAL_RETURN_DAYS:
        b.law("LEG-CDC-049").cite("POL-DEV-001", 5).note(
            f"A entrega foi há {days} dias: está no prazo legal de arrependimento de 7 dias (LEG-CDC-049)."
        )
        b.legal_basis = "LEG-CDC-049"
    elif days is not None and days <= window:
        b.cite("POL-DEV-001", 2, 5).note(
            f"A entrega foi há {days} dias: dentro da janela de {window} dias da versão {v.version} "
            "da política, vigente na data da compra."
        )
    else:
        b.cite("POL-DEV-001", 2).note(
            f"A entrega foi há {days} dias, após a janela de {window} dias; o pedido não é negado."
        ).to_human()
        return
    b.request, b.return_reason, b.policy_version = "devolucao", "arrependimento", v.version
    b.note("Devolução registrada; as instruções de postagem ou coleta seguem pelo canal de atendimento.")
    if s.total_paid > HIGH_VALUE:
        b.cite("POL-REF-001", 3).note(
            "Valor acima de R$ 1.000,00: o reembolso exige aprovação humana."
        ).to_human()


def _product(b: _Builder, s: OrderSummary, intent: str, signals: Set[Signal]) -> None:
    if s.stage is not Stage.ENTREGUE:
        b.cite("POL-ENT-002", 1)
        _delivery(b, s, "consultar_prazo")
        return
    if intent in ("produto_errado", "pedido_incompleto"):
        b.cite("POL-PRD-001", 1, 3).ticket("divergencia_produto", escalate=True)
        b.note("Pedir descrição e, se possível, fotos do produto, da embalagem e da etiqueta.")
        if len({i.seller_id for i in s.items}) > 1:
            b.cite("POL-PRD-001", 2).note("O pedido tem mais de um vendedor; identificar o item afetado.")
        return
    b.cite("POL-PRD-002", 1, 2, 3).law("LEG-CDC-026").ticket("defeito_produto", escalate=True)
    b.note("Registrar o defeito, quando foi percebido e as evidências; não fazer diagnóstico técnico.")
    if s.days_since_delivery is not None and s.days_since_delivery > 30:
        b.note("Passaram mais de 30 dias da entrega: o caso vai para revisão humana e não é negado.")
    if Signal.RISCO_SAUDE in signals:
        b.cite("POL-PRD-002", 4).note("Orientar o cliente a interromper o uso do produto imediatamente.")


def _refund(b: _Builder, s: OrderSummary, refund_status: str | None) -> None:
    b.cite("POL-REF-001", 1)
    if refund_status is None:
        b.note("Não há solicitação de reembolso registrada para este pedido; não supor que exista.")
    else:
        b.note(f"Status do reembolso registrado: {refund_status}. Só dizer que foi pago se for 'processado'.")
    b.cite("POL-REF-001", 2)
    if any(p.type == "not_defined" for p in s.payments):
        b.note("Há pagamento com meio não definido.").to_human()


def _billing(b: _Builder, s: OrderSummary, signals: Set[Signal]) -> None:
    b.cite("POL-PAG-001", 1).note(
        "Pagamentos do pedido: "
        + "; ".join(f"{p.type}, {p.installments}x, R$ {p.value}" for p in s.payments)
        + f". Total pago: R$ {s.total_paid}."
    )
    if Signal.VALOR_DIFERENTE in signals:
        b.cite("POL-PAG-001", 2).ticket("cobranca", escalate=True)
        b.note("Não afirmar que houve erro nem acerto na cobrança.")
    if Signal.COBRANCA_NAO_RECONHECIDA in signals:
        b.cite("POL-PAG-001", 3).ticket("cobranca", escalate=True)
    if signals & {Signal.VALOR_DIFERENTE, Signal.COBRANCA_NAO_RECONHECIDA}:
        b.note("Nunca pedir número de cartão, código de segurança, senha ou dados bancários.")


def _service(b: _Builder, tickets: list[TicketRow], today: date) -> None:
    b.cite("POL-SLA-001", 1, 2)
    open_ = [t for t in tickets if t.ticket_status not in ("resolvido", "encerrado")]
    overdue = [
        t
        for t in open_
        if (today - t.ticket_opened_at.date()).days
        > TICKET_UPDATE_DAYS.get(t.ticket_type, DEFAULT_UPDATE_DAYS)
    ]
    if overdue:
        b.ticket("reclamacao_atendimento", escalate=True).note(
            "Há ocorrência aberta com prazo de atualização vencido."
        )
    elif open_:
        b.note("Há ocorrência aberta dentro do prazo de atualização.")
    else:
        b.note("Não há ocorrência registrada; oferecer a abertura de uma.")


# ---------------------------------------------------------------- entrada


def decide(
    intent: str,
    summary: OrderSummary,
    kb: KnowledgeBase,
    *,
    signals: Set[Signal] = frozenset(),
    refund_status: str | None = None,
    tickets: list[TicketRow] | None = None,
) -> Decision:
    b = _Builder(kb, summary.purchase_date)
    if summary.stage is Stage.INCONSISTENTE and intent not in ("elogio_ou_satisfacao", "outro_ou_ambiguo"):
        b.cite("POL-ENT-002", 4).note(
            "Os dados do pedido são inconsistentes; não afirmar o estágio."
        ).to_human()
    elif intent in ("consultar_prazo", "entrega_atrasada", "pedido_nao_recebido"):
        _delivery(b, summary, intent)
    elif intent in ("produto_errado", "pedido_incompleto", "produto_com_defeito", "produto_danificado"):
        _product(b, summary, intent, signals)
    elif intent == "devolver_produto":
        b.cite("POL-DEV-001", 4).note("Perguntar o motivo da devolução antes de aplicar a política.")
    elif intent == "arrependimento":
        _return(b, summary)
    elif intent == "cancelar_pedido":
        _cancel(b, summary)
    elif intent == "reembolso":
        _refund(b, summary, refund_status)
    elif intent == "cobranca_pagamento":
        _billing(b, summary, signals)
    elif intent == "reclamar_do_atendimento":
        _service(b, tickets or [], summary.reference_date)
    elif intent == "elogio_ou_satisfacao":
        b.note("Agradecer o retorno do cliente.")
    else:  # outro_ou_ambiguo ou intenção desconhecida
        b.note("Pedir que o cliente descreva o que precisa sobre o pedido.")

    if signals & {Signal.RISCO_SAUDE, Signal.JURIDICO, Signal.COBRANCA_NAO_RECONHECIDA}:
        b.to_human()
    return b.build()
