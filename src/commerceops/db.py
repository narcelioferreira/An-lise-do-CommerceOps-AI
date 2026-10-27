"""Acesso ao Postgres. Toda consulta é parametrizada; o LLM nunca escreve SQL."""

from __future__ import annotations

from psycopg.rows import class_row
from psycopg_pool import ConnectionPool

from commerceops.tools.orders import ItemRow, OrderRow, PaymentRow


class PostgresOrderRepository:
    def __init__(self, pool: ConnectionPool) -> None:
        self.pool = pool

    def get_order(self, order_id: str) -> OrderRow | None:
        with self.pool.connection() as conn, conn.cursor(row_factory=class_row(OrderRow)) as cur:
            cur.execute(
                """
                SELECT o.order_id, c.customer_unique_id, c.customer_zip_code_prefix, o.order_status,
                       o.order_purchase_timestamp, o.order_approved_at, o.order_delivered_carrier_date,
                       o.order_delivered_customer_date, o.order_estimated_delivery_date
                FROM olist.orders o JOIN olist.customers c USING (customer_id)
                WHERE o.order_id = %s
                """,
                (order_id,),
            )
            return cur.fetchone()

    def get_items(self, order_id: str) -> list[ItemRow]:
        with self.pool.connection() as conn, conn.cursor(row_factory=class_row(ItemRow)) as cur:
            cur.execute(
                """
                SELECT i.order_item_id, p.product_category_name, i.seller_id, i.shipping_limit_date,
                       i.price, i.freight_value
                FROM olist.order_items i JOIN olist.products p USING (product_id)
                WHERE i.order_id = %s ORDER BY i.order_item_id
                """,
                (order_id,),
            )
            return cur.fetchall()

    def get_payments(self, order_id: str) -> list[PaymentRow]:
        with self.pool.connection() as conn, conn.cursor(row_factory=class_row(PaymentRow)) as cur:
            cur.execute(
                """
                SELECT payment_sequential, payment_type, payment_installments, payment_value
                FROM olist.order_payments WHERE order_id = %s ORDER BY payment_sequential
                """,
                (order_id,),
            )
            return cur.fetchall()

    def record_action(self, tool_name: str, order_id_hash: str | None, allowed: bool, reason: str) -> None:
        from langfuse import get_client

        with self.pool.connection() as conn:
            conn.execute(
                "INSERT INTO sim.agent_actions (trace_id, tool_name, order_id_hash, allowed, reason) "
                "VALUES (%s, %s, %s, %s, %s)",
                (get_client().get_current_trace_id(), tool_name, order_id_hash, allowed, reason),
            )

    def ping(self) -> None:
        with self.pool.connection() as conn:
            conn.execute("SELECT 1")
