"""Gera os números do painel (reports/dashboard/dados.json) a partir dos CSVs e de reports/eval/.

Uso:
    python scripts/dashboard_data.py [--raw data/raw]

Operação: dados reais da Olist na janela analítica (compra entre 2017-01-01 e 2018-08-31).
Agente: lido dos relatórios de avaliação já publicados, sem nova chamada ao LLM.
"""

import argparse
import json
from pathlib import Path

import pandas as pd
import yaml

from commerceops.data.audit import WINDOW, load

ROOT = Path(__file__).resolve().parents[1]
EXCLUIDOS = {"canceled", "unavailable"}
E3 = {
    "gpt-oss-120b": "agente-openai_gpt-oss-120b-20261027-090833.json",
    "gpt-oss-20b": "agente-openai_gpt-oss-20b-20261027-091345.json",
}
E1 = "retrieval-bge-m3-20261026-235001.json"
EXEMPLOS = [
    "ENT-003-atraso-grave-01",
    "PRD-002-defeito-com-risco-01",
    "SEG-001-injecao-de-prompt-01",
    "DEV-001-caso-limite-versao-01",
]


def operacao(raw: Path) -> dict:
    t = load(raw).tables
    o, items, pay, rev = t["orders"], t["items"], t["payments"], t["reviews"]
    o = o[o.order_purchase_timestamp.between(WINDOW[0], f"{WINDOW[1]} 23:59:59")].copy()
    o["mes"] = o.order_purchase_timestamp.dt.strftime("%Y-%m")
    validos = o[~o.order_status.isin(EXCLUIDOS)]

    it = items[items.order_id.isin(validos.order_id)].copy()
    it["valor"] = it.price + it.freight_value
    receita_pedido = it.groupby("order_id").valor.sum()

    # D2: compara datas, não timestamps (a previsão é sempre meia-noite).
    ent = o[o.order_delivered_customer_date.notna()].copy()
    ent["atraso_dias"] = (
        ent.order_delivered_customer_date.dt.normalize() - ent.order_estimated_delivery_date
    ).dt.days
    ent["atrasado"] = ent.atraso_dias > 0
    ent["dias_entrega"] = (
        ent.order_delivered_customer_date.dt.normalize() - ent.order_purchase_timestamp.dt.normalize()
    ).dt.days

    # review_id não é único; a nota do pedido é a média das linhas de avaliação dele.
    nota = rev.groupby("order_id").review_score.mean()
    ent["nota"] = ent.order_id.map(nota)

    mensal = (
        o.groupby("mes")
        .agg(pedidos=("order_id", "size"))
        .join(
            validos.assign(receita=validos.order_id.map(receita_pedido)).groupby("mes").receita.sum().round(2)
        )
        .join(ent.groupby("mes").atrasado.mean().round(4).rename("taxa_atraso"))
        .reset_index()
    )

    cust = t["customers"].set_index("customer_id")
    ent["uf"] = ent.customer_id.map(cust.customer_state)
    por_uf = (
        ent.groupby("uf")
        .agg(
            entregues=("order_id", "size"), taxa_atraso=("atrasado", "mean"), dias=("dias_entrega", "median")
        )
        .sort_values("entregues", ascending=False)
        .head(12)
        .round(4)
        .reset_index()
    )

    prod = t["products"].set_index("product_id").product_category_name
    it["categoria"] = it.product_id.map(prod).fillna("sem_categoria")
    cat = it.groupby("categoria").valor.sum().sort_values(ascending=False).head(10).round(2)

    pg = pay[pay.order_id.isin(validos.order_id)]
    pag = (pg.groupby("payment_type").payment_value.sum() / pg.payment_value.sum()).round(4)

    notas_linhas = rev[rev.order_id.isin(o.order_id)].review_score.value_counts().sort_index()
    nota_por_atraso = ent.groupby(
        pd.cut(ent.atraso_dias, [-1000, 0, 5, 1000], labels=["no_prazo", "ate_5d", "mais_5d"])
    ).nota.agg(["mean", "size"])

    receita = float(receita_pedido.sum())
    return {
        "janela": {"de": WINDOW[0], "ate": WINDOW[1]},
        "kpis": {
            "pedidos": int(len(o)),
            "clientes_unicos": int(o.customer_id.map(cust.customer_unique_id).nunique()),
            "receita": round(receita, 2),
            "ticket_medio": round(receita / len(receita_pedido), 2),
            "entregues": int(len(ent)),
            "taxa_atraso": round(float(ent.atrasado.mean()), 4),
            "taxa_atraso_mais_5d": round(float((ent.atraso_dias > 5).mean()), 4),
            "dias_entrega_mediana": float(ent.dias_entrega.median()),
            "nota_media": round(float(rev[rev.order_id.isin(o.order_id)].review_score.mean()), 2),
        },
        "mensal": mensal.to_dict(orient="records"),
        "por_uf": por_uf.to_dict(orient="records"),
        "categorias": [{"categoria": k, "receita": v} for k, v in cat.items()],
        "pagamentos": {k: float(v) for k, v in pag.sort_values(ascending=False).items()},
        "notas": {str(k): int(v) for k, v in notas_linhas.items()},
        "nota_por_atraso": [
            {"faixa": str(k), "nota_media": round(float(r["mean"]), 2), "pedidos": int(r["size"])}
            for k, r in nota_por_atraso.iterrows()
        ],
    }


def agente(eval_dir: Path) -> dict:
    e3 = {}
    for modelo, nome in E3.items():
        d = json.loads((eval_dir / nome).read_text(encoding="utf-8"))
        e3[modelo] = {"arquivo": nome, "resumo": d["resumo"], "cenarios": len(d["cenarios"])}
    e1 = json.loads((eval_dir / E1).read_text(encoding="utf-8"))
    # Exemplos do modelo padrão; order_id e CEP ficam de fora (as imagens são públicas).
    cenarios = {c["scenario_id"]: c for c in yaml.safe_load((ROOT / "evals" / "scenarios.yaml").read_text())}
    saidas = json.loads((eval_dir / E3["gpt-oss-120b"]).read_text(encoding="utf-8"))["cenarios"]
    exemplos = []
    for s in saidas:
        if s["scenario_id"] in EXEMPLOS:
            c, out = cenarios[s["scenario_id"]], s["output"]
            exemplos.append(
                {
                    "scenario_id": s["scenario_id"],
                    "reference_date": str(c["reference_date"]),
                    "mensagem": c["customer_message"],
                }
                | {k: out[k] for k in ("answer", "intent", "escalated", "actions", "policy_ids", "validated")}
            )
    return {
        "e1": {"arquivo": E1, "k": e1["k"], "por_metodo": e1["por_metodo"]},
        "e3": e3,
        "exemplos": exemplos,
    }


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--raw", type=Path, default=ROOT / "data" / "raw")
    a = p.parse_args()
    out = ROOT / "reports" / "dashboard" / "dados.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    dados = {"operacao": operacao(a.raw), "agente": agente(ROOT / "reports" / "eval")}
    texto = json.dumps(dados, ensure_ascii=False, indent=2)
    out.write_text(texto, encoding="utf-8")
    # As páginas do painel leem os dados como script, para abrirem direto do disco.
    out.with_suffix(".js").write_text(f"window.DADOS = {texto};\n", encoding="utf-8")
    print(json.dumps(dados["operacao"]["kpis"], ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
