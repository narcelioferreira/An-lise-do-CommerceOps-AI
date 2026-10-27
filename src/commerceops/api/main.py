"""API HTTP do CommerceOps AI.

Health checks seguem a divisão combinada para o Kubernetes:
- /health/live  : o processo responde (liveness probe)
- /health/ready : o Postgres responde (readiness probe)
- /health/deep  : Postgres + LLM + Langfuse, para monitoramento. NUNCA usar como probe:
                  uma instabilidade do provedor de LLM tiraria todos os pods do ar ao mesmo tempo.
"""

from __future__ import annotations

import time
from collections.abc import Iterator
from contextlib import asynccontextmanager
from datetime import date
from typing import Annotated

import httpx
from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from langfuse import Langfuse, propagate_attributes
from psycopg_pool import ConnectionPool
from pydantic import BaseModel, Field

from commerceops.agent import Agent, ChatRequest, ChatResult, build_agent
from commerceops.config import Settings, get_settings
from commerceops.observability import init_langfuse
from commerceops.tools.orders import (
    OrderAccessDenied,
    OrderRepository,
    OrderSummary,
    get_order_summary,
    verify_customer,
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    app.state.langfuse = init_langfuse(settings)
    pool = ConnectionPool(settings.database_url.get_secret_value(), min_size=1, max_size=5, open=False)
    pool.open(wait=False)
    app.state.agent = build_agent(settings, pool)
    app.state.repo = app.state.agent.repo
    try:
        yield
    finally:
        app.state.langfuse.flush()
        pool.close()


# Documentação interativa só fora de produção: em produção ela só amplia a superfície exposta.
_docs = get_settings().environment != "production"
app = FastAPI(
    title="CommerceOps AI",
    version="0.1.0",
    lifespan=lifespan,
    docs_url="/docs" if _docs else None,
    redoc_url=None,
    openapi_url="/openapi.json" if _docs else None,
)

SECURITY_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "no-referrer",
    "Cache-Control": "no-store",  # respostas trazem dados do pedido
}


@app.middleware("http")
async def security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers.update(SECURITY_HEADERS)
    return response


def get_repo(request: Request) -> Iterator[OrderRepository]:
    yield request.app.state.repo


def get_langfuse(request: Request) -> Langfuse:
    return request.app.state.langfuse


def get_agent(request: Request) -> Agent:
    return request.app.state.agent


class RateLimiter:
    """Janela fixa por IP, em memória (OWASP Unbounded consumption).

    Também torna inviável testar CEPs em massa contra um pedido conhecido (o dataset é público).
    Por pod: no Kubernetes, o limite global fica no ingress (k8s/).
    """

    MAX_KEYS = 10_000

    def __init__(self, limit: int, window_s: int = 60) -> None:
        self.limit, self.window = limit, window_s
        self.hits: dict[str, tuple[int, int]] = {}

    def __call__(self, request: Request) -> None:
        key = request.client.host if request.client else "desconhecido"
        slot = int(time.monotonic() // self.window)
        if len(self.hits) > self.MAX_KEYS:
            self.hits = {k: v for k, v in self.hits.items() if v[0] == slot}
        prev_slot, count = self.hits.get(key, (slot, 0))
        count = count + 1 if prev_slot == slot else 1
        self.hits[key] = (slot, count)
        if count > self.limit:
            raise HTTPException(
                status_code=429, detail="muitas requisições", headers={"Retry-After": str(self.window)}
            )


rate_limit = RateLimiter(get_settings().rate_limit_per_minute)


# ---------------------------------------------------------------- health


@app.get("/health/live")
def live() -> dict:
    return {"status": "ok"}


@app.get("/health/ready")
def ready(repo: Annotated[OrderRepository, Depends(get_repo)]) -> JSONResponse:
    try:
        repo.ping()  # type: ignore[attr-defined]
    except Exception:
        return JSONResponse({"status": "unavailable", "database": "erro"}, status_code=503)
    return JSONResponse({"status": "ok", "database": "ok"})


@app.get("/health/deep")
def deep(
    repo: Annotated[OrderRepository, Depends(get_repo)],
    lf: Annotated[Langfuse, Depends(get_langfuse)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> dict:
    checks: dict[str, str] = {}
    try:
        repo.ping()  # type: ignore[attr-defined]
        checks["database"] = "ok"
    except Exception:
        checks["database"] = "erro"

    if settings.llm_base_url:
        try:
            # /models existe no Groq e no Ollama (API compatível com OpenAI) e não consome tokens
            headers = (
                {"Authorization": f"Bearer {settings.llm_api_key.get_secret_value()}"}
                if settings.llm_api_key
                else {}
            )
            httpx.get(
                f"{settings.llm_base_url.rstrip('/')}/models", headers=headers, timeout=3
            ).raise_for_status()
            checks["llm"] = "ok"
        except httpx.HTTPError:
            checks["llm"] = "erro"
    else:
        checks["llm"] = "não configurado"

    if settings.langfuse_enabled:
        try:
            checks["langfuse"] = "ok" if lf.auth_check() else "erro"
        except Exception:
            checks["langfuse"] = "erro"
    else:
        checks["langfuse"] = "desligado"

    degraded = any(v == "erro" for v in checks.values())
    return {"status": "degraded" if degraded else "ok", "checks": checks}


# ---------------------------------------------------------------- pedidos


class OrderLookupRequest(BaseModel):
    order_id: str = Field(min_length=1, max_length=64)
    zip_prefix: str = Field(min_length=5, max_length=9, description="5 primeiros dígitos do CEP")
    reference_date: date = Field(description="'Hoje' no ambiente simulado (decisão D4)")


@app.post("/v1/orders/lookup", response_model=OrderSummary, dependencies=[Depends(rate_limit)])
def order_lookup(
    body: OrderLookupRequest,
    repo: Annotated[OrderRepository, Depends(get_repo)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> OrderSummary:
    key = settings.order_id_hmac_key.get_secret_value()
    with propagate_attributes(
        trace_name="order_lookup",
        tags=["api", "order_lookup"],
        metadata={"reference_date": body.reference_date.isoformat()},
    ):
        try:
            customer = verify_customer(repo, body.order_id, body.zip_prefix, hmac_key=key)
            return get_order_summary(repo, customer, body.order_id, body.reference_date, hmac_key=key)
        except OrderAccessDenied as e:
            # 404 para os dois casos: não revela se o pedido existe
            raise HTTPException(status_code=404, detail=str(e)) from None


@app.post("/v1/chat", response_model=ChatResult, dependencies=[Depends(rate_limit)])
def chat(
    body: ChatRequest,
    agent: Annotated[Agent, Depends(get_agent)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> ChatResult:
    with propagate_attributes(
        trace_name="chat",
        tags=["api", "chat"] + (["avaliacao"] if body.scenario_id else []),
        metadata={"reference_date": body.reference_date.isoformat(), "release": settings.release},
    ):
        try:
            return agent.answer(body)
        except OrderAccessDenied as e:
            raise HTTPException(status_code=404, detail=str(e)) from None
