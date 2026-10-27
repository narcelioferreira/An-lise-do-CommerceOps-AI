"""Avaliação: cenários simulados, métricas por cenário e métricas de busca.

Todas as métricas são determinísticas (gabarito no cenário). Avaliação por LLM, se um dia entrar,
será sinal auxiliar e nunca o único gabarito (pacote de políticas, seção 8.4).
"""

from __future__ import annotations

from collections import defaultdict
from datetime import date
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, ConfigDict

from commerceops.agent import ChatResult

DEFAULT_SCENARIOS = Path(__file__).resolve().parents[2] / "evals" / "scenarios.yaml"


class Scenario(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    scenario_id: str
    simulated: Literal[True]
    inspired_by_review_row_id: int | None = None
    reference_date: date
    order_id: str
    zip_prefix: str
    customer_message: str
    expected_intent: str | None
    expected_sentiment: str | None = None
    access_denied: bool = False
    expected_policy_ids: list[str]
    expected_chunk_ids: list[str]
    expected_actions: list[str]
    must_escalate: bool
    must_not_say: list[str]


def load_scenarios(path: Path = DEFAULT_SCENARIOS) -> list[Scenario]:
    scenarios = [Scenario.model_validate(s) for s in yaml.safe_load(path.read_text(encoding="utf-8"))]
    ids = [s.scenario_id for s in scenarios]
    if len(ids) != len(set(ids)):
        raise ValueError("scenario_id duplicado")
    return scenarios


def score(s: Scenario, result: ChatResult | None) -> dict[str, float]:
    """`result` None = acesso negado. Cada métrica vale 0 ou 1, exceto o recall de políticas.

    Se o LLM falhou (timeout, 429), o cenário conta só em `falha_de_infra`: a resposta degradada não
    diz nada sobre a qualidade do modelo e não pode entrar nas outras médias.
    """
    if s.access_denied or result is None:
        return {"acesso_negado_correto": float(s.access_denied and result is None)}
    if result.llm_failures:
        return {"falha_de_infra": 1.0}
    expected = set(s.expected_policy_ids)
    answer = result.answer.lower()
    return {
        "intencao_correta": float(result.intent == s.expected_intent),
        "politicas_recall": len(expected & set(result.policy_ids)) / len(expected) if expected else 1.0,
        "encaminhamento_correto": float(result.escalated == s.must_escalate),
        "acoes_corretas": float(set(result.actions) == set(s.expected_actions)),
        "sem_frase_proibida": float(not any(p.lower() in answer for p in s.must_not_say)),
        "resposta_validada": float(result.validated),
        "falha_de_infra": 0.0,
    }


def retrieval_score(ranked_ids: list[str], expected: list[str], k: int) -> dict[str, float]:
    top = ranked_ids[:k]
    first = next((i for i, c in enumerate(top, start=1) if c in expected), None)
    return {
        f"recall@{k}": len(set(top) & set(expected)) / len(expected),
        f"mrr@{k}": 1 / first if first else 0.0,
    }


def summarize(rows: list[dict[str, float]]) -> dict[str, dict[str, float]]:
    """Média e n de cada métrica (cada uma só conta os cenários em que se aplica)."""
    values: dict[str, list[float]] = defaultdict(list)
    for row in rows:
        for name, v in row.items():
            values[name].append(v)
    return {name: {"media": round(sum(v) / len(v), 4), "n": len(v)} for name, v in sorted(values.items())}
