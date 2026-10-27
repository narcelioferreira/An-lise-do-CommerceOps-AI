"""Carga dos CSVs do Olist no schema `olist`. Tratamentos documentados em scripts/load_olist.py."""

from __future__ import annotations

import time
from pathlib import Path

import pandas as pd
import psycopg
from psycopg import sql

from commerceops.data.audit import FILES

ZIP = {"customer_zip_code_prefix": str, "seller_zip_code_prefix": str}

# Ordem respeita as chaves estrangeiras.
TABLES = [
    "customers",
    "sellers",
    "category_translation",
    "products",
    "orders",
    "order_items",
    "order_payments",
    "order_reviews",
]


def read(raw: Path, key: str) -> pd.DataFrame:
    return pd.read_csv(raw / FILES[key], encoding="utf-8-sig", dtype=ZIP)


def prepare(raw: Path) -> dict[str, pd.DataFrame]:
    products = read(raw, "products").rename(
        columns={
            "product_name_lenght": "product_name_length",
            "product_description_lenght": "product_description_length",
        }
    )
    # 610 produtos sem medidas: com NaN o pandas vira float ("40.0") e o COPY para integer falha
    int_cols = products.columns.drop(["product_id", "product_category_name"])
    products[int_cols] = products[int_cols].astype("Int64")
    reviews = read(raw, "reviews")
    reviews.insert(0, "review_row_id", range(1, len(reviews) + 1))
    reviews["review_creation_date"] = pd.to_datetime(reviews.review_creation_date).dt.date
    reviews["review_id_duplicate"] = reviews.review_id.duplicated(keep=False)
    orders = read(raw, "orders")
    orders["order_estimated_delivery_date"] = pd.to_datetime(orders.order_estimated_delivery_date).dt.date
    return {
        "customers": read(raw, "customers"),
        "sellers": read(raw, "sellers"),
        "category_translation": read(raw, "translation"),
        "products": products,
        "orders": orders,
        "order_items": read(raw, "items"),
        "order_payments": read(raw, "payments"),
        "order_reviews": reviews,
    }


def _rows(df: pd.DataFrame):
    for row in df.itertuples(index=False, name=None):
        yield tuple(None if pd.isna(v) else v for v in row)


def load(conn: psycopg.Connection, frames: dict[str, pd.DataFrame]) -> None:
    with conn.transaction():
        tables = [sql.Identifier("olist", t) for t in TABLES]
        conn.execute(sql.SQL("TRUNCATE {} CASCADE").format(sql.SQL(", ").join(tables)))
        for table, ident in zip(TABLES, tables, strict=True):
            df = frames[table]
            # Nomes de coluna vêm do cabeçalho do CSV (dado externo): sempre como identificador citado
            copy_sql = sql.SQL("COPY {} ({}) FROM STDIN").format(
                ident, sql.SQL(", ").join(map(sql.Identifier, df.columns))
            )
            t0 = time.perf_counter()
            with conn.cursor().copy(copy_sql) as copy:
                for row in _rows(df):
                    copy.write_row(row)
            print(f"olist.{table:<22} {len(df):>9,} linhas  {time.perf_counter() - t0:5.1f}s")
