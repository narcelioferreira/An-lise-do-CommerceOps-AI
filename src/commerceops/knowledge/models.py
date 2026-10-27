"""Modelos da base de conhecimento: taxonomia, políticas fictícias e fontes legais."""

from __future__ import annotations

import re
from datetime import date
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

POLICY_ID_RE = re.compile(r"^POL-[A-Z]{3}-\d{3}$")
LEGAL_ID_RE = re.compile(r"^LEG-CDC-\d{3}$")
SECTION_ID_RE = re.compile(r"^(POL-[A-Z]{3}-\d{3})-S\d{2}$")

# Campos que uma política pode exigir. Colunas reais do Olist + campos do schema `sim`.
OLIST_FIELDS = frozenset(
    {
        "order_id",
        "order_status",
        "order_purchase_timestamp",
        "order_approved_at",
        "order_delivered_carrier_date",
        "order_delivered_customer_date",
        "order_estimated_delivery_date",
        "customer_zip_code_prefix",
        "customer_unique_id",
        "order_item_id",
        "product_id",
        "product_category_name",
        "seller_id",
        "shipping_limit_date",
        "price",
        "freight_value",
        "payment_sequential",
        "payment_type",
        "payment_installments",
        "payment_value",
    }
)
SIM_FIELDS = frozenset({"refund_status", "ticket_status", "ticket_opened_at"})
KNOWN_FIELDS = OLIST_FIELDS | SIM_FIELDS


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class Intent(_Strict):
    id: str
    group: Literal["entrega", "produto", "pedido", "financeiro", "atendimento", "outro"]
    description: str
    include: list[str] = Field(default_factory=list)
    exclude: str = ""
    policies: list[str] = Field(default_factory=list)

    @field_validator("id")
    @classmethod
    def _ascii_snake(cls, v: str) -> str:
        if not re.fullmatch(r"[a-z][a-z0-9_]*", v):
            raise ValueError(f"id de intenção deve ser ASCII snake_case: {v!r}")
        return v


class DerivedFlag(_Strict):
    id: str
    rule: str


class Taxonomy(_Strict):
    version: str
    intents: list[Intent]
    cross_cutting_policies: list[str]
    derived_flags: list[DerivedFlag]
    sentiments: list[str]

    @property
    def intent_ids(self) -> set[str]:
        return {i.id for i in self.intents}


class Section(_Strict):
    section_id: str
    title: str
    requires_order_data: list[str] = Field(default_factory=list)
    escalation: Literal["none", "conditional", "required"]
    text: str

    @field_validator("requires_order_data")
    @classmethod
    def _known_fields(cls, v: list[str]) -> list[str]:
        unknown = set(v) - KNOWN_FIELDS
        if unknown:
            raise ValueError(f"campos desconhecidos em requires_order_data: {sorted(unknown)}")
        return v


class PolicyVersion(_Strict):
    version: str
    effective_from: date
    effective_until: date | None = None
    # Números que as regras em código usam (ex.: return_window_days). O texto da seção diz o mesmo
    # número para o leitor; um teste garante que os dois não divergem.
    params: dict[str, int] = Field(default_factory=dict)
    sections: list[Section]

    @model_validator(mode="after")
    def _check(self) -> PolicyVersion:
        if self.effective_until and self.effective_until < self.effective_from:
            raise ValueError(f"versão {self.version}: effective_until anterior a effective_from")
        ids = [s.section_id for s in self.sections]
        if len(ids) != len(set(ids)):
            raise ValueError(f"versão {self.version}: section_id duplicado")
        return self

    def is_active_on(self, day: date) -> bool:
        return self.effective_from <= day and (self.effective_until is None or day <= self.effective_until)


class Policy(_Strict):
    policy_id: str
    title: str
    category: str
    source_type: Literal["fictional_policy"]
    fictional: Literal[True]
    intents: list[str]
    related: list[str] = Field(default_factory=list)
    versions: list[PolicyVersion]

    @model_validator(mode="after")
    def _check(self) -> Policy:
        if not POLICY_ID_RE.fullmatch(self.policy_id):
            raise ValueError(f"policy_id fora do padrão: {self.policy_id}")
        for v in self.versions:
            for s in v.sections:
                m = SECTION_ID_RE.fullmatch(s.section_id)
                if not m or m.group(1) != self.policy_id:
                    raise ValueError(f"{s.section_id} não pertence a {self.policy_id}")
        ordered = sorted(self.versions, key=lambda v: v.effective_from)
        for prev, nxt in zip(ordered, ordered[1:], strict=False):
            if prev.effective_until is None or prev.effective_until >= nxt.effective_from:
                raise ValueError(f"{self.policy_id}: vigências das versões se sobrepõem")
        return self

    def version_on(self, day: date) -> PolicyVersion | None:
        """Versão vigente numa data. Para POL-DEV-001, a data relevante é a da compra."""
        return next((v for v in self.versions if v.is_active_on(day)), None)


class LegalArticle(_Strict):
    legal_id: str
    article: str
    topic: str
    verification_status: Literal["pendente", "verificado"]
    verified_at: date | None = None
    related_policies: list[str] = Field(default_factory=list)
    text: str

    @model_validator(mode="after")
    def _check(self) -> LegalArticle:
        if not LEGAL_ID_RE.fullmatch(self.legal_id):
            raise ValueError(f"legal_id fora do padrão: {self.legal_id}")
        if self.verification_status == "verificado" and self.verified_at is None:
            raise ValueError(f"{self.legal_id}: verificado sem verified_at")
        return self


class LegalSource(_Strict):
    source_type: Literal["legal_public_source"]
    fictional: Literal[False]
    law: str
    official_url: str
    articles: list[LegalArticle]


class Chunk(_Strict):
    """Unidade indexada no RAG: uma seção de uma versão de política, ou um artigo de lei."""

    chunk_id: str  # section_id@version ou legal_id
    doc_id: str  # policy_id ou legal_id
    version: str | None
    source_type: Literal["fictional_policy", "legal_public_source"]
    fictional: bool
    title: str
    effective_from: date | None
    effective_until: date | None
    intents: list[str]
    escalation: Literal["none", "conditional", "required"]
    text: str
