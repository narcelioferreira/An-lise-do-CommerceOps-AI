"""Roda a avaliação sobre evals/scenarios.yaml e grava o resultado em reports/eval/.

Uso (DATABASE_URL apontando para um banco com o dataset real carregado):
    python scripts/run_eval.py                   # agente completo com LLM_MODEL (desenvolvimento)
    python scripts/run_eval.py --oficial         # rodada oficial, com LLM_MODEL_OFICIAL
    python scripts/run_eval.py --oracle-intent   # intenção do gabarito: mede decisão, ações e redação
    python scripts/run_eval.py --retrieval       # Recall@k e MRR@k da busca, por método

Com LLM_CACHE_PATH, respostas já obtidas vêm do cache e não gastam tokens; para medir a variação
entre execuções, rode com LLM_CACHE_PATH= (vazio).

Com LANGFUSE_* configurado, cada execução vira um experimento no Langfuse, com scores por cenário.
"""

from __future__ import annotations

import argparse
import dataclasses
import json
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from langfuse import Evaluation, Langfuse  # noqa: E402
from psycopg_pool import ConnectionPool  # noqa: E402

from commerceops.agent import Agent, ChatRequest, ChatResult, build_agent  # noqa: E402
from commerceops.config import get_settings  # noqa: E402
from commerceops.evaluation import (  # noqa: E402
    Scenario,
    eval_model,
    load_scenarios,
    retrieval_score,
    score,
    summarize,
)
from commerceops.knowledge.retrieval import Method  # noqa: E402
from commerceops.llm import ChatModel  # noqa: E402
from commerceops.observability import init_langfuse  # noqa: E402
from commerceops.tools.orders import OrderAccessDenied  # noqa: E402

K = 5


def oracle_chat(intents: dict[str, str | None], inner: ChatModel | None) -> ChatModel:
    """Classificação pelo gabarito; a redação continua com o LLM configurado, se houver."""

    def chat(messages: list[dict[str, str]], *, json_mode: bool, name: str) -> str:
        if name == "classificar":
            message = json.loads(messages[-1]["content"])["mensagem"]
            return json.dumps({"intent": intents[message], "confidence": 1.0})
        return inner(messages, json_mode=json_mode, name=name) if inner else ""

    return chat


def run_agent(
    langfuse: Langfuse, agent: Agent, scenarios: list[Scenario], run_name: str, metadata: dict
) -> list[dict]:
    by_id = {s.scenario_id: s for s in scenarios}

    def task(*, item, **_):
        s = by_id[item["input"]["scenario_id"]]
        req = ChatRequest(
            order_id=s.order_id,
            zip_prefix=s.zip_prefix,
            reference_date=s.reference_date,
            message=s.customer_message,
            scenario_id=s.scenario_id,
        )
        try:
            result = agent.answer(req)
        except OrderAccessDenied:
            return None
        # campos de diagnóstico ficam fora do model_dump (exclude) e entram só no relatório
        return result.model_dump(mode="json") | {
            "llm_failures": result.llm_failures,
            "validation_errors": result.validation_errors,
            "rejected_draft": result.rejected_draft,
        }

    def evaluator(*, input, output, **_):
        result = ChatResult.model_validate(output) if output else None
        return [Evaluation(name=n, value=v) for n, v in score(by_id[input["scenario_id"]], result).items()]

    experiment = langfuse.run_experiment(
        name="cenarios-v1",
        run_name=run_name,
        data=[{"input": {"scenario_id": s.scenario_id}, "metadata": {"simulated": True}} for s in scenarios],
        task=task,
        evaluators=[evaluator],
        max_concurrency=1,  # cenários compartilham pedidos, e o plano gratuito do LLM limita requisições
        metadata=metadata,
    )
    langfuse.flush()
    return [
        {
            "scenario_id": r.item["input"]["scenario_id"],
            "scores": {e.name: e.value for e in r.evaluations},
            "output": r.output,
        }
        for r in experiment.item_results
    ]


def run_retrieval(agent: Agent, scenarios: list[Scenario]) -> dict:
    methods = list(Method) if agent.retriever.embed else [Method.LEXICAL]
    out = {}
    for method in methods:
        rows = []
        for s in scenarios:
            row = agent.repo.get_order(s.order_id)
            if not s.expected_chunk_ids or row is None:
                continue
            hits = agent.retriever.search(
                s.customer_message, day=row.order_purchase_timestamp.date(), method=method, k=K
            )
            rows.append(retrieval_score([h.chunk_id for h in hits], s.expected_chunk_ids, K))
        out[method.value] = summarize(rows)
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    mode = ap.add_mutually_exclusive_group()
    mode.add_argument("--oracle-intent", action="store_true")
    mode.add_argument("--retrieval", action="store_true")
    ap.add_argument("--oficial", action="store_true", help="usa LLM_MODEL_OFICIAL (rodadas oficiais)")
    ap.add_argument("--out-dir", type=Path, default=ROOT / "reports" / "eval")
    args = ap.parse_args()

    settings = get_settings()
    if not args.retrieval:
        try:
            model = eval_model(settings.llm_model, settings.llm_model_oficial, oficial=args.oficial)
        except ValueError as e:
            print(e, file=sys.stderr)
            return 2
        settings = settings.model_copy(update={"llm_model": model})
    # Antes de qualquer chamada: langfuse.openai instrumenta o SDK do OpenAI inteiro, inclusive embeddings
    langfuse = init_langfuse(settings)
    scenarios = load_scenarios()
    with ConnectionPool(settings.database_url.get_secret_value(), min_size=1, max_size=2) as pool:
        agent = build_agent(settings, pool)
        name = "retrieval" if args.retrieval else "oracle-intent" if args.oracle_intent else "agente"
        name += "-oficial" if args.oficial else ""
        if agent.chat is None and name == "agente":
            print("LLM não configurado: use --oracle-intent ou defina LLM_*", file=sys.stderr)
            return 2
        metadata = {
            "modo": name,
            "llm_model": settings.llm_model or "nenhum",
            "embedding_model": settings.embedding_model or "nenhum",
            "release": settings.release,
            "oficial": args.oficial,
            "cache": bool(settings.llm_cache_path),
        }
        model = metadata["embedding_model" if args.retrieval else "llm_model"].replace("/", "_")
        run_name = f"{name}-{model}-{datetime.now():%Y%m%d-%H%M%S}"
        if args.retrieval:
            report = {**metadata, "k": K, "por_metodo": run_retrieval(agent, scenarios)}
        else:
            if args.oracle_intent:
                intents = {s.customer_message: s.expected_intent for s in scenarios}
                agent = dataclasses.replace(agent, chat=oracle_chat(intents, agent.chat))
            results = run_agent(
                langfuse, agent, scenarios, run_name, {k: str(v) for k, v in metadata.items()}
            )
            report = {**metadata, "resumo": summarize([r["scores"] for r in results]), "cenarios": results}

    args.out_dir.mkdir(parents=True, exist_ok=True)
    path = args.out_dir / f"{run_name}.json"
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report.get("resumo") or report["por_metodo"], ensure_ascii=False, indent=2))
    print(f"gravado em {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
