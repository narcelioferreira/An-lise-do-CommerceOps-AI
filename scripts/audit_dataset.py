"""Auditoria reprodutível do dataset Olist.

Uso:
    python scripts/audit_dataset.py --raw-dir data/raw --out-dir reports/audit

Gera audit.json (completo) e audit.md (resumo em tabelas). Só grava estatísticas agregadas:
nenhum texto de avaliação nem identificador sai daqui.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from commerceops.data.audit import load, run  # noqa: E402


def _fmt(v) -> str:
    if isinstance(v, float):
        return f"{v:.2%}" if 0 < abs(v) < 1 else f"{v:,.2f}"
    if isinstance(v, int):
        return f"{v:,}".replace(",", ".")
    return str(v)


def _table(rows: list[tuple], header: tuple) -> list[str]:
    out = ["| " + " | ".join(header) + " |", "|" + "---|" * len(header)]
    out += ["| " + " | ".join(_fmt(c) for c in row) + " |" for row in rows]
    return out + [""]


def to_markdown(a: dict) -> str:
    o, c, r, rt, d, ip, cat = (
        a["orders"],
        a["customers"],
        a["reviews"],
        a["review_timing"],
        a["delivery"],
        a["items_payments"],
        a["catalog"],
    )
    L = [
        "<!-- Gerado por scripts/audit_dataset.py. Não editar à mão. -->",
        "",
        f"# Auditoria do dataset Olist (v{a['audit_version']})",
        "",
        "## Arquivos",
        "",
    ]
    L += _table(
        [
            (
                n,
                f.get("rows", "—"),
                f.get("cols", "—"),
                "sim" if f.get("bom") else "não",
                f.get("status", "ok"),
            )
            for n, f in a["files"].items()
        ],
        ("Arquivo", "Linhas", "Colunas", "BOM", "Status"),
    )
    L += ["## Pedidos", ""]
    L += _table(list(o["stage"].items()), ("Estágio calculado", "Pedidos"))
    L += _table(list(o["inconsistent_reasons"].items()), ("Inconsistência", "Pedidos"))
    w = o["analytical_window"]
    L += [
        f"Janela analítica {w['from']} a {w['to']}: {_fmt(w['orders_in'])} pedidos dentro, "
        f"{_fmt(w['orders_out'])} fora.",
        "",
    ]
    L += _table(list(o["monthly_volume"].items()), ("Mês da compra", "Pedidos"))
    L += ["## Clientes", ""]
    L += _table(list(c.items()), ("Métrica", "Valor"))
    L += ["## Avaliações", ""]
    L += _table(
        [
            (k, r[k])
            for k in (
                "rows",
                "review_id_unique",
                "review_id_duplicated_rows",
                "review_id_in_gt1_order",
                "with_message",
                "with_title",
                "with_title_or_message",
            )
        ],
        ("Métrica", "Valor"),
    )
    L += _table(list(r["message_length_nonempty"].items()), ("Tamanho da mensagem (não vazia)", "Caracteres"))
    L += _table(list(r["creation_time_of_day"].items()), ("Horário em review_creation_date", "Linhas"))
    L += _table(
        [(s, v["with_text"], v["total"], v["rate"]) for s, v in r["text_rate_by_score"].items()],
        ("Nota", "Com texto", "Total", "Taxa"),
    )
    L += _table(list(r["with_text_by_order_status"].items()), ("Status do pedido", "Avaliações com texto"))
    L += ["## Avaliação × eventos do pedido", "", f"_{rt['note']}_", ""]
    L += _table(
        [
            (k, rt[k]["by_timestamp"], rt[k]["by_date"])
            for k in ("before_purchase", "before_delivery", "before_delivery_with_text")
        ],
        ("Avaliações criadas…", "Por timestamp", "Por data"),
    )
    L += ["## Entrega", "", f"_{d['note']}_", ""]
    L += _table(
        [(k, d["all"][k], d["analytical_window"][k]) for k in d["analytical_window"]],
        ("Métrica", "Todos", "Janela analítica"),
    )
    L += _table(list(d["dispatched_after_seller_limit"].items()), ("Despacho × prazo do vendedor", "Valor"))
    L += ["## Itens e pagamentos", ""]
    L += _table([(k, v) for k, v in ip["items"].items() if not isinstance(v, dict)], ("Itens", "Valor"))
    L += _table(
        list(ip["items"]["orders_without_items_by_status"].items()), ("Pedido sem itens — status", "Pedidos")
    )
    L += _table(
        [(k, v) for k, v in ip["payments"].items() if not isinstance(v, dict)], ("Pagamentos", "Valor")
    )
    L += _table(list(ip["payments"]["types"].items()), ("Meio de pagamento", "Registros"))
    L += _table(list(ip["payments"]["value"].items()), ("payment_value", "R$"))
    L += [f"_{ip['payment_vs_items']['note']}_", ""]
    L += _table(
        [(k, v) for k, v in ip["payment_vs_items"].items() if k != "note"], ("Pagamento × itens", "Pedidos")
    )
    L += ["## Catálogo", ""]
    L += _table(
        [
            (k, v if not isinstance(v, (list, dict)) else ", ".join(map(str, v)))
            for k, v in cat.items()
            if k != "geolocation"
        ],
        ("Métrica", "Valor"),
    )
    if "geolocation" in cat:
        L += _table(list(cat["geolocation"].items()), ("Geolocalização", "Valor"))
    return "\n".join(L).rstrip() + "\n"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--raw-dir", type=Path, default=ROOT / "data" / "raw")
    ap.add_argument("--out-dir", type=Path, default=ROOT / "reports" / "audit")
    args = ap.parse_args()

    result = run(load(args.raw_dir))
    args.out_dir.mkdir(parents=True, exist_ok=True)
    (args.out_dir / "audit.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    (args.out_dir / "audit.md").write_text(to_markdown(result), encoding="utf-8")
    print(f"auditoria gravada em {args.out_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
