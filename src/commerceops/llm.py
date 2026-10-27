"""Clientes de LLM e de embeddings com API compatível com OpenAI (decisão D9)."""

from __future__ import annotations

from typing import Protocol

from langfuse.openai import OpenAI as TracedOpenAI
from openai import OpenAI

from commerceops.config import Settings
from commerceops.knowledge.retrieval import Embedder

# Limites explícitos: provedor lento ou fora do ar não pode prender a requisição (OWASP ASI08)
TIMEOUT_S = 20
MAX_RETRIES = 2
# Teto de saída por chamada (OWASP Unbounded consumption). Modelos de raciocínio gastam parte dele pensando.
MAX_OUTPUT_TOKENS = 2048


class ChatModel(Protocol):
    def __call__(self, messages: list[dict[str, str]], *, json_mode: bool, name: str) -> str: ...


def make_chat(settings: Settings) -> ChatModel | None:
    """Cliente de chat com tracing do Langfuse (tokens, latência e custo por geração)."""
    if not (settings.llm_base_url and settings.llm_model and settings.llm_api_key):
        return None
    client = TracedOpenAI(
        base_url=settings.llm_base_url,
        api_key=settings.llm_api_key.get_secret_value(),
        timeout=TIMEOUT_S,
        max_retries=settings.llm_max_retries,
    )
    model = settings.llm_model

    def chat(messages: list[dict[str, str]], *, json_mode: bool, name: str) -> str:
        extra = {"response_format": {"type": "json_object"}} if json_mode else {}
        response = client.chat.completions.create(
            model=model,
            messages=messages,  # type: ignore[arg-type]
            temperature=0,
            max_completion_tokens=MAX_OUTPUT_TOKENS,
            name=name,
            **extra,
        )
        return response.choices[0].message.content or ""

    return chat


def make_embedder(settings: Settings) -> Embedder | None:
    """Sem configuração de embeddings, só a busca lexical fica disponível."""
    if not (settings.embedding_base_url and settings.embedding_model):
        return None
    key = settings.embedding_api_key.get_secret_value() if settings.embedding_api_key else "sem-chave"
    client = OpenAI(
        base_url=settings.embedding_base_url, api_key=key, timeout=TIMEOUT_S, max_retries=MAX_RETRIES
    )
    model = settings.embedding_model

    def embed(texts: list[str]) -> list[list[float]]:
        data = client.embeddings.create(model=model, input=texts).data
        return [d.embedding for d in sorted(data, key=lambda d: d.index)]

    return embed
