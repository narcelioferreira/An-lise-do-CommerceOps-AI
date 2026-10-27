"""Auditoria reprodutível do dataset Olist (v2).

Diferenças em relação à v1 (audit.py original):
- caminhos por argumento; cada CSV é lido uma única vez;
- toda comparação temporal é feita nas duas granularidades (timestamp e data) e rotulada,
  porque misturá-las gerou números incoerentes no parecer (5.127 por data × 4.576 por timestamp);
- calcula também os números citados no parecer que a v1 não calculava;
- comprimento de mensagem só sobre textos não vazios;
- verificações novas: BOM, resíduo de fuso, cliente real (customer_unique_id), estágio do pedido,
  despacho após o prazo do vendedor, pagamento × itens, categorias sem tradução.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pandas as pd

from commerceops.domain.orders import SEVERE_DELAY_DAYS, order_stage

FILES = {
    "customers": "olist_customers_dataset.csv",
    "geolocation": "olist_geolocation_dataset.csv",
    "items": "olist_order_items_dataset.csv",
    "payments": "olist_order_payments_dataset.csv",
    "reviews": "olist_order_reviews_dataset.csv",
    "orders": "olist_orders_dataset.csv",
    "products": "olist_products_dataset.csv",
    "sellers": "olist_sellers_dataset.csv",
    "translation": "product_category_name_translation.csv",
}
OPTIONAL = {"geolocation"}
ORDER_DATES = [
    "order_purchase_timestamp",
    "order_approved_at",
    "order_delivered_carrier_date",
    "order_delivered_customer_date",
    "order_estimated_delivery_date",
]
# Janela analítica: meses com volume contínuo (ver docs/02_auditoria_dados.md).
WINDOW = ("2017-01-01", "2018-08-31")


@dataclass
class Dataset:
    tables: dict[str, pd.DataFrame]
    bom: dict[str, bool]
    missing: list[str]


def _has_bom(path: Path) -> bool:
    with path.open("rb") as f:
        return f.read(3) == b"\xef\xbb\xbf"


def load(raw_dir: Path) -> Dataset:
    tables, bom, missing = {}, {}, []
    for key, name in FILES.items():
        path = raw_dir / name
        if not path.exists():
            if key in OPTIONAL:
                missing.append(name)
                continue
            raise FileNotFoundError(path)
        bom[name] = _has_bom(path)
        tables[key] = pd.read_csv(path, encoding="utf-8-sig")
    o = tables["orders"]
    for c in ORDER_DATES:
        o[c] = pd.to_datetime(o[c])
    r = tables["reviews"]
    r["review_creation_date"] = pd.to_datetime(r["review_creation_date"])
    r["review_answer_timestamp"] = pd.to_datetime(r["review_answer_timestamp"])
    tables["items"]["shipping_limit_date"] = pd.to_datetime(tables["items"]["shipping_limit_date"])
    return Dataset(tables, bom, missing)


def _nonempty(s: pd.Series) -> pd.Series:
    return s.fillna("").str.strip().ne("")


def _q(s: pd.Series, qs=(0.5, 0.9, 0.99)) -> dict[str, float]:
    return {f"p{int(q * 100)}": round(float(s.quantile(q)), 2) for q in qs}


def _counts(s: pd.Series) -> dict[str, int]:
    return {str(k): int(v) for k, v in s.value_counts(dropna=False).items()}


def files_section(ds: Dataset) -> dict:
    return {
        FILES[k]: {
            "rows": len(df),
            "cols": len(df.columns),
            "bom": ds.bom[FILES[k]],
            "nulls": {c: int(n) for c, n in df.isna().sum().items() if n},
        }
        for k, df in ds.tables.items()
    } | {name: {"status": "não carregado"} for name in ds.missing}


def orders_section(o: pd.DataFrame) -> dict:
    month = o.order_purchase_timestamp.dt.to_period("M").astype(str)
    in_window = o.order_purchase_timestamp.between(WINDOW[0], f"{WINDOW[1]} 23:59:59")
    stages = [
        order_stage(s, None if pd.isna(c) else c, None if pd.isna(d) else d)
        for s, c, d in zip(
            o.order_status, o.order_delivered_carrier_date, o.order_delivered_customer_date, strict=True
        )
    ]
    return {
        "rows": len(o),
        "status": _counts(o.order_status),
        "date_ranges": {c: [str(o[c].min()), str(o[c].max()), int(o[c].isna().sum())] for c in ORDER_DATES},
        "monthly_volume": {k: int(v) for k, v in month.value_counts().sort_index().items()},
        "analytical_window": {
            "from": WINDOW[0],
            "to": WINDOW[1],
            "orders_in": int(in_window.sum()),
            "orders_out": int((~in_window).sum()),
        },
        "stage": _counts(pd.Series([s.stage.value for s in stages])),
        "inconsistent_reasons": _counts(pd.Series([s.reasons[0] for s in stages if s.reasons], dtype=str)),
    }


def customers_section(o: pd.DataFrame, c: pd.DataFrame) -> dict:
    per_customer = o.merge(c, on="customer_id").groupby("customer_unique_id").size()
    return {
        "customer_id_unique": int(c.customer_id.nunique()),
        "customer_id_equals_orders": bool(c.customer_id.nunique() == o.order_id.nunique()),
        "customer_unique_id": int(c.customer_unique_id.nunique()),
        "customers_with_gt1_order": int((per_customer > 1).sum()),
        "max_orders_per_customer": int(per_customer.max()),
    }


def reviews_section(r: pd.DataFrame, o: pd.DataFrame) -> dict:
    msg, title = _nonempty(r.review_comment_message), _nonempty(r.review_comment_title)
    has_text = msg | title
    lengths = r.loc[msg, "review_comment_message"].str.strip().str.len()
    per_order = r.groupby("order_id").size()
    orders_per_review_id = r.groupby("review_id").order_id.nunique()
    hour = r.review_creation_date.dt.strftime("%H:%M:%S")
    by_score = r.assign(has_text=has_text).groupby("review_score").has_text.agg(["sum", "count"])
    status = r[["order_id"]].merge(o[["order_id", "order_status"]], on="order_id", how="left").order_status
    return {
        "rows": len(r),
        "review_id_unique": int(r.review_id.nunique()),
        "review_id_duplicated_rows": int(r.review_id.duplicated().sum()),
        "review_id_in_gt1_order": int((orders_per_review_id > 1).sum()),
        "orders_with_review": int(r.order_id.nunique()),
        "reviews_per_order": {str(k): int(v) for k, v in per_order.value_counts().sort_index().items()},
        "with_message": int(msg.sum()),
        "with_title": int(title.sum()),
        "with_title_or_message": int(has_text.sum()),
        "message_length_nonempty": _q(lengths) | {"max": int(lengths.max()), "n": int(len(lengths))},
        "creation_time_of_day": _counts(hour),
        "score": {str(k): int(v) for k, v in r.review_score.value_counts().sort_index().items()},
        "text_rate_by_score": {
            str(s): {
                "with_text": int(row["sum"]),
                "total": int(row["count"]),
                "rate": round(float(row["sum"] / row["count"]), 3),
            }
            for s, row in by_score.iterrows()
        },
        "with_text_by_order_status": _counts(status[has_text.values]),
        "creation_range": [
            str(r.review_creation_date.min().date()),
            str(r.review_creation_date.max().date()),
        ],
    }


def review_timing_section(r: pd.DataFrame, o: pd.DataFrame) -> dict:
    """Avaliação × eventos do pedido, nas duas granularidades (ver D2 em docs/01_politicas_v1.1.md)."""
    m = r.merge(o, on="order_id")
    has_text = (_nonempty(m.review_comment_message) | _nonempty(m.review_comment_title)).values
    rc, rd = m.review_creation_date, m.review_creation_date.dt.normalize()
    delivered = (m.order_status == "delivered").values & m.order_delivered_customer_date.notna().values
    dcust = m.order_delivered_customer_date

    def both(mask_ts, mask_date):
        return {"by_timestamp": int(mask_ts.sum()), "by_date": int(mask_date.sum())}

    before_purchase_ts = rc < m.order_purchase_timestamp
    before_purchase_d = rd < m.order_purchase_timestamp.dt.normalize()
    before_delivery_ts = delivered & (rc < dcust).values
    before_delivery_d = delivered & (rd < dcust.dt.normalize()).values
    days = (m.review_creation_date - m.order_purchase_timestamp).dt.total_seconds() / 86400
    return {
        "note": (
            "by_date é a medida de referência; by_timestamp superestima porque a avaliação é sempre 00:00"
        ),
        "before_purchase": both(before_purchase_ts, before_purchase_d),
        "delivered_reviews": int(delivered.sum()),
        "before_delivery": both(before_delivery_ts, before_delivery_d),
        "before_delivery_with_text": both(before_delivery_ts & has_text, before_delivery_d & has_text),
        "purchase_to_review_days": _q(days.dropna(), (0.01, 0.5, 0.9, 0.99)),
    }


def delivery_section(o: pd.DataFrame, items: pd.DataFrame) -> dict:
    obs = o[o.order_delivered_customer_date.notna()]
    late = (obs.order_delivered_customer_date.dt.normalize() - obs.order_estimated_delivery_date).dt.days
    in_window = obs.order_purchase_timestamp.between(WINDOW[0], f"{WINDOW[1]} 23:59:59")
    limit = items.groupby("order_id").shipping_limit_date.max().rename("shipping_limit")
    ship = o.merge(limit, on="order_id")
    shipped = ship[ship.order_delivered_carrier_date.notna()]
    dispatched_late = (
        shipped.order_delivered_carrier_date.dt.normalize() > shipped.shipping_limit.dt.normalize()
    )

    def rates(days: pd.Series) -> dict:
        return {
            "n": int(len(days)),
            "late": int((days > 0).sum()),
            "late_rate": round(float((days > 0).mean()), 4),
            f"late_gt_{SEVERE_DELAY_DAYS}d": int((days > SEVERE_DELAY_DAYS).sum()),
            f"late_gt_{SEVERE_DELAY_DAYS}d_rate": round(float((days > SEVERE_DELAY_DAYS).mean()), 4),
        }

    return {
        "note": "dias corridos, comparando datas (entrega normalizada × previsão)",
        "all": rates(late) | {"days_quantiles": _q(late, (0.01, 0.1, 0.5, 0.9, 0.99))},
        "analytical_window": rates(late[in_window]),
        "dispatched_after_seller_limit": {
            "orders_with_carrier_date": int(len(shipped)),
            "late_dispatch": int(dispatched_late.sum()),
            "rate": round(float(dispatched_late.mean()), 4),
        },
    }


def items_payments_section(o, items, pay) -> dict:
    per_order = items.groupby("order_id")
    no_items = o[~o.order_id.isin(items.order_id)]
    pay_total = pay.groupby("order_id").payment_value.sum()
    items_total = (items.price + items.freight_value).groupby(items.order_id).sum()
    diff = (pay_total - items_total).dropna()
    return {
        "items": {
            "rows": len(items),
            "orders": int(items.order_id.nunique()),
            "orders_gt1_item": int((per_order.size() > 1).sum()),
            "orders_gt1_seller": int((per_order.seller_id.nunique() > 1).sum()),
            "orders_without_items_by_status": _counts(no_items.order_status),
        },
        "payments": {
            "rows": len(pay),
            "orders": int(pay.order_id.nunique()),
            "orders_without_payment": int((~o.order_id.isin(pay.order_id)).sum()),
            "types": _counts(pay.payment_type),
            "installments_zero": int((pay.payment_installments == 0).sum()),
            "orders_gt1_payment_row": int((pay.groupby("order_id").size() > 1).sum()),
            "orders_gt1_payment_type": int((pay.groupby("order_id").payment_type.nunique() > 1).sum()),
            "value": _q(pay.payment_value),
            "orders_paid_gt_1000": int((pay_total > 1000).sum()),
        },
        "payment_vs_items": {
            "note": "soma dos pagamentos − soma de preço+frete; diferença não implica erro (juros, voucher)",
            "orders_compared": int(len(diff)),
            "abs_diff_gt_1_real": int((diff.abs() > 1).sum()),
            "paid_more": int((diff > 1).sum()),
            "paid_less": int((diff < -1).sum()),
        },
    }


def catalog_section(ds: Dataset) -> dict:
    t = ds.tables
    products, translation, sellers = t["products"], t["translation"], t["sellers"]
    cats = set(products.product_category_name.dropna())
    out = {
        "products": len(products),
        "products_without_category": int(products.product_category_name.isna().sum()),
        "categories": len(cats),
        "categories_without_translation": sorted(cats - set(translation.product_category_name)),
        "sellers": len(sellers),
        "items_with_unknown_seller": int((~t["items"].seller_id.isin(sellers.seller_id)).sum()),
        "seller_state_top5": {k: int(v) for k, v in sellers.seller_state.value_counts().head(5).items()},
    }
    if "geolocation" in t:
        g = t["geolocation"]
        out["geolocation"] = {
            "rows": len(g),
            "zip_prefixes": int(g.geolocation_zip_code_prefix.nunique()),
            "rows_per_prefix_mean": round(len(g) / g.geolocation_zip_code_prefix.nunique(), 1),
        }
    return out


def run(ds: Dataset) -> dict:
    t = ds.tables
    return {
        "audit_version": "2.0",
        "files": files_section(ds),
        "orders": orders_section(t["orders"]),
        "customers": customers_section(t["orders"], t["customers"]),
        "reviews": reviews_section(t["reviews"], t["orders"]),
        "review_timing": review_timing_section(t["reviews"], t["orders"]),
        "delivery": delivery_section(t["orders"], t["items"]),
        "items_payments": items_payments_section(t["orders"], t["items"], t["payments"]),
        "catalog": catalog_section(ds),
    }
