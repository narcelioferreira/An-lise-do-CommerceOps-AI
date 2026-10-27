"""Extrai do Langfuse os números de observabilidade do E3 (reports/dashboard/langfuse.json).

Uso:
    python scripts/langfuse_data.py

Lê as observações das rodadas oficiais do E3 pela API pública (só leitura) e grava latência por passo,
tokens por geração e um trace de exemplo. Não chama o LLM. Metadados do SDK (inclusive a chave
pública) ficam de fora, e o exemplo só traz campos que já chegaram mascarados ao Langfuse.
"""

import json
import statistics as st
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

import httpx

from commerceops.config import get_settings

ROOT = Path(__file__).resolve().parents[1]
# Os nomes dos relatórios usam a hora local de quem rodou o E3 (UTC-3).
FUSO = timezone(timedelta(hours=-3))
RODADAS = {
    "gpt-oss-120b": "agente-openai_gpt-oss-120b-20261027-090833.json",
    "gpt-oss-20b": "agente-openai_gpt-oss-20b-20261027-091345.json",
}
EXEMPLO = ("gpt-oss-120b", "ENT-003-atraso-grave-01")
PASSOS = [
    "verify_customer",
    "get_order_summary",
    "classificar",
    "contextualizar",
    "OpenAI-embedding",
    "redigir",
]


def inicio(arquivo: str) -> datetime:
    data, hora = arquivo.removesuffix(".json").split("-")[-2:]
    return datetime.strptime(data + hora, "%Y%m%d%H%M%S").replace(tzinfo=FUSO)


def observacoes(c: httpx.Client, de: datetime, ate: datetime, **extra) -> list[dict]:
    out, cursor = [], None
    while True:
        p = {"fromStartTime": de.isoformat(), "toStartTime": ate.isoformat(), "limit": 100} | extra
        if cursor:
            p["cursor"] = cursor
        r = c.get("/api/public/v2/observations", params=p)
        if r.status_code != 200:
            raise SystemExit(f"Langfuse respondeu HTTP {r.status_code}")
        j = r.json()
        out += j["data"]
        cursor = j["meta"].get("cursor")
        if not cursor or not j["data"]:
            return out


def p90(v: list[float]) -> float:
    v = sorted(v)
    return v[min(len(v) - 1, round(0.9 * (len(v) - 1)))]


def resumo(obs: list[dict], traces: set[str]) -> dict:
    lat, tok = defaultdict(list), defaultdict(list)
    for o in obs:
        if o["traceId"] not in traces or o.get("latency") is None:
            continue
        # classificar e redigir aparecem como span e como geração; vale a geração (chamada ao LLM).
        if o["name"] in ("classificar", "redigir") and o["type"] != "GENERATION":
            continue
        lat[o["name"]].append(o["latency"])
        if o["type"] == "GENERATION":
            u = o.get("usageDetails") or {}
            tok[o["name"]].append(
                (u.get("input", 0), u.get("output", 0), u.get("output_reasoning_tokens", 0))
            )
    total = sum(lat["atendimento"])
    llm = sum(lat["classificar"]) + sum(lat["redigir"])
    return {
        "traces": len(lat["atendimento"]),
        "ponta_a_ponta": {"mediana": st.median(lat["atendimento"]), "p90": p90(lat["atendimento"])},
        "passos": {
            p: {"n": len(lat[p]), "mediana": round(st.median(lat[p]), 4), "p90": round(p90(lat[p]), 4)}
            for p in PASSOS
        },
        "fracao_llm": round(llm / total, 4),
        "tokens": {
            g: {
                "entrada": st.median(x[0] for x in v),
                "saida": st.median(x[1] for x in v),
                "raciocinio": st.median(x[2] for x in v),
            }
            for g, v in tok.items()
        },
    }


def exemplo(c: httpx.Client, de: datetime, trace_id: str) -> dict:
    obs = observacoes(c, de, de + timedelta(minutes=20), traceId=trace_id, fields="core,basic,io,model")
    raiz = next(o for o in obs if o["name"] == "atendimento")
    t0 = datetime.fromisoformat(raiz["startTime"])
    por_id = {o["id"]: o for o in obs}

    def nivel(o: dict) -> int:
        n = 0
        while o["id"] != raiz["id"] and o.get("parentObservationId") in por_id:
            o, n = por_id[o["parentObservationId"]], n + 1
        return n

    passos = []
    for o in sorted(obs, key=lambda o: o["startTime"]):
        if o["name"].startswith(("experiment-", "evaluator")) or (o is not raiz and nivel(o) == 0):
            continue
        ini = (datetime.fromisoformat(o["startTime"]) - t0).total_seconds()
        passos.append(
            {
                "nome": o["name"],
                "tipo": o["type"],
                "nivel": nivel(o),
                "inicio": round(ini, 3),
                "duracao": round(o.get("latency") or 0, 3),
                "modelo": o.get("model"),
            }
        )
    io = {o["name"]: o for o in obs if o["name"] in ("get_order_summary", "classificar") and o.get("output")}
    return {
        "scenario_id": EXEMPLO[1],
        "passos": passos,
        "consulta": {
            "entrada": json.loads(io["get_order_summary"]["input"]),
            "saida": json.loads(io["get_order_summary"]["output"]),
        },
        "classificacao": json.loads(io["classificar"]["output"]),
    }


def main() -> None:
    s = get_settings()
    if not s.langfuse_enabled:
        raise SystemExit("Defina LANGFUSE_PUBLIC_KEY e LANGFUSE_SECRET_KEY.")
    auth = (s.langfuse_public_key, s.langfuse_secret_key.get_secret_value())
    out = {"rodadas": {}}
    with httpx.Client(base_url=s.langfuse_base_url, auth=auth, timeout=30) as c:
        for modelo, arquivo in RODADAS.items():
            de = inicio(arquivo)
            obs = observacoes(c, de, de + timedelta(minutes=20), fields="core,basic,usage,model,metadata")
            runs = [
                o
                for o in obs
                if o["name"] == "experiment-item-run"
                and (o.get("metadata") or {}).get("llm_model", "").endswith(modelo)
            ]
            out["rodadas"][modelo] = {"relatorio": arquivo} | resumo(obs, {o["traceId"] for o in runs})
            if modelo == EXEMPLO[0]:
                itens = observacoes(
                    c, de, de + timedelta(minutes=20), name="experiment-item-run", fields="core,io"
                )
                # A janela de 20 min alcança a rodada seguinte; só valem os traces deste modelo.
                proprios = {o["traceId"] for o in runs}
                alvo = next(
                    o for o in itens if o["traceId"] in proprios and EXEMPLO[1] in (o.get("input") or "")
                )
                out["exemplo"] = exemplo(c, de, alvo["traceId"])
    dest = ROOT / "reports" / "dashboard" / "langfuse.json"
    texto = json.dumps(out, ensure_ascii=False, indent=2)
    dest.write_text(texto, encoding="utf-8")
    dest.with_suffix(".js").write_text(f"window.LANGFUSE = {texto};\n", encoding="utf-8")
    print(
        json.dumps(
            {
                m: {k: r[k] for k in ("traces", "ponta_a_ponta", "fracao_llm")}
                for m, r in out["rodadas"].items()
            }
        )
    )


if __name__ == "__main__":
    main()
