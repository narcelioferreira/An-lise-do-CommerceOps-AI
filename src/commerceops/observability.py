"""Langfuse e pseudonimização de identificadores."""

from __future__ import annotations

import hashlib
import hmac
import logging
import re
from typing import Any

from langfuse import Langfuse

from commerceops.config import Settings

log = logging.getLogger(__name__)

# Aplicado a todo input/output/metadata antes de sair para o Langfuse (OWASP LLM02).
# IDs do Olist têm 32 hex; o HMAC de hash_id tem 16 e passa intacto, de propósito.
_PII_PATTERNS = [
    (re.compile(r"\b[0-9a-f]{32}\b", re.IGNORECASE), "<id>"),
    (re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+"), "<email>"),
    (re.compile(r"(?<![+\w])(?:\d[ -]?){13,19}\b"), "<cartao>"),
    (re.compile(r"\b\d{3}\.?\d{3}\.?\d{3}-?\d{2}\b"), "<cpf>"),
    (re.compile(r"\b\d{5}-?\d{3}\b"), "<cep>"),
    (re.compile(r"(?<!\w)(?:\+?55\s?)?\(?\d{2}\)?\s?9?\d{4}-?\d{4}\b"), "<telefone>"),
]


def mask_pii(*, data: Any, **_: Any) -> Any:
    if isinstance(data, str):
        for pattern, label in _PII_PATTERNS:
            data = pattern.sub(label, data)
        return data
    if isinstance(data, dict):
        return {k: mask_pii(data=v) for k, v in data.items()}
    if isinstance(data, list | tuple):
        return [mask_pii(data=v) for v in data]
    return data


def init_langfuse(settings: Settings) -> Langfuse:
    """Cria o cliente global do Langfuse. Sem chaves, devolve um cliente com tracing desligado.

    Uma falha do Langfuse nunca deve derrubar o atendimento: ele é observabilidade, não dependência.
    """
    if not settings.langfuse_enabled:
        log.warning("Langfuse sem chaves: tracing desligado")
        return Langfuse(public_key="disabled", secret_key="disabled", tracing_enabled=False)  # noqa: S106
    return Langfuse(
        public_key=settings.langfuse_public_key,
        secret_key=settings.langfuse_secret_key.get_secret_value(),  # type: ignore[union-attr]
        base_url=settings.langfuse_base_url,
        environment=settings.environment,
        release=settings.release,
        mask=mask_pii,
    )


def hash_id(value: str, key: str) -> str:
    """HMAC-SHA256 truncado. Hash simples seria reversível: o dataset com os IDs é público."""
    return hmac.new(key.encode(), value.encode(), hashlib.sha256).hexdigest()[:16]
