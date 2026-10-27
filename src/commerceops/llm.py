"""Clientes de LLM e de embeddings com API compatível com OpenAI (decisão D9)."""

from __future__ import annotations

import hashlib
import json
import sqlite3
import threading
from pathlib import Path
from typing import Protocol

from langfuse import get_client
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


class ResponseCache:
    """Respostas reais do LLM em SQLite local: a mesma chamada nunca vai ao provedor duas vezes.

    Só para desenvolvimento e avaliação (economia de tokens). Guarda o hash da requisição e o texto da
    resposta; erros não entram. Para medir variação entre execuções, rode sem LLM_CACHE_PATH.
    """

    def __init__(self, path: str) -> None:
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        self.lock = threading.Lock()  # a API atende em várias threads
        self.conn = sqlite3.connect(path, check_same_thread=False)
        self.conn.execute(
            "CREATE TABLE IF NOT EXISTS respostas (chave TEXT PRIMARY KEY, modelo TEXT NOT NULL,"
            " resposta TEXT NOT NULL, criado_em TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)"
        )

    @staticmethod
    def key(**request: object) -> str:
        return hashlib.sha256(json.dumps(request, sort_keys=True, ensure_ascii=False).encode()).hexdigest()

    def get(self, key: str) -> str | None:
        with self.lock:
            row = self.conn.execute("SELECT resposta FROM respostas WHERE chave = ?", (key,)).fetchone()
        return row[0] if row else None

    def put(self, key: str, model: str, response: str) -> None:
        with self.lock, self.conn:
            self.conn.execute(
                "INSERT OR IGNORE INTO respostas (chave, modelo, resposta) VALUES (?, ?, ?)",
                (key, model, response),
            )


def cached(chat: ChatModel, cache: ResponseCache, model: str) -> ChatModel:
    def chat_with_cache(messages: list[dict[str, str]], *, json_mode: bool, name: str) -> str:
        # Tudo que muda a resposta entra na chave; `name` só nomeia o span
        key = ResponseCache.key(
            model=model, messages=messages, json_mode=json_mode, temperature=0, max_tokens=MAX_OUTPUT_TOKENS
        )
        hit = cache.get(key)
        if hit is not None:
            get_client().update_current_span(metadata={"llm_cache": "hit"})
            return hit
        response = chat(messages, json_mode=json_mode, name=name)
        cache.put(key, model, response)
        return response

    return chat_with_cache


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

    return cached(chat, ResponseCache(settings.llm_cache_path), model) if settings.llm_cache_path else chat


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
