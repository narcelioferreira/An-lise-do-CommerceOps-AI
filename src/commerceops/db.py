"""Acesso ao Postgres. Toda consulta é parametrizada; o LLM nunca escreve SQL."""

from __future__ import annotations

from datetime import date, datetime

from psycopg import sql
from psycopg.rows import class_row
from psycopg_pool import ConnectionPool

from commerceops.domain.decisions import TicketRow
from commerceops.knowledge.retrieval import ChunkRow
from commerceops.tools.orders import ItemRow, OrderRow, PaymentRow

_OWNED = sql.SQL("""
    WITH owned AS (
        SELECT o.order_id FROM olist.orders o JOIN olist.customers c USING (customer_id)
        WHERE o.order_id = %(order_id)s AND c.customer_unique_id = %(customer)s
    )
""")


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

    # ------------------------------------------------------------ schema sim (simulado)
    # Toda escrita parte de _OWNED: sem posse do pedido pelo cliente verificado, nada é gravado (ASI03).
    # Os índices únicos parciais tornam as escritas idempotentes; o encaminhamento só sobe.

    def open_ticket(
        self,
        customer_unique_id: str,
        order_id: str,
        ticket_type: str,
        escalated: bool,
        policy_ids: list[str],
        opened_at: datetime,
        scenario_id: str | None,
    ) -> int | None:
        return self._one(
            _OWNED
            + sql.SQL("""
            INSERT INTO sim.tickets (scenario_id, order_id, customer_unique_id, ticket_type, escalated,
                                     policy_ids, ticket_opened_at)
            SELECT %(scenario)s, order_id, %(customer)s, %(type)s, %(escalated)s, %(policies)s, %(at)s
            FROM owned
            ON CONFLICT (order_id, ticket_type) WHERE ticket_status NOT IN ('resolvido', 'encerrado')
            DO UPDATE SET escalated = sim.tickets.escalated OR EXCLUDED.escalated
            RETURNING ticket_id
            """),
            {
                "customer": customer_unique_id,
                "order_id": order_id,
                "type": ticket_type,
                "escalated": escalated,
                "policies": policy_ids,
                "at": opened_at,
                "scenario": scenario_id,
            },
        )

    def request_cancellation(
        self, customer_unique_id: str, order_id: str, requested_at: datetime
    ) -> int | None:
        return self._one(
            _OWNED
            + sql.SQL("""
            INSERT INTO sim.cancellation_requests (order_id, requested_at) SELECT order_id, %(at)s FROM owned
            ON CONFLICT (order_id) WHERE status = 'solicitado'
            DO UPDATE SET requested_at = sim.cancellation_requests.requested_at
            RETURNING request_id
            """),
            {"customer": customer_unique_id, "order_id": order_id, "at": requested_at},
        )

    def request_return(
        self,
        customer_unique_id: str,
        order_id: str,
        reason: str | None,
        legal_basis: str | None,
        policy_version: str | None,
        requested_at: datetime,
    ) -> int | None:
        return self._one(
            _OWNED
            + sql.SQL("""
            INSERT INTO sim.return_requests (order_id, reason, legal_basis, policy_version, requested_at)
            SELECT order_id, %(reason)s, %(legal)s, %(version)s, %(at)s FROM owned
            ON CONFLICT (order_id) WHERE status IN ('solicitado', 'em_analise')
            DO UPDATE SET requested_at = sim.return_requests.requested_at
            RETURNING request_id
            """),
            {
                "customer": customer_unique_id,
                "order_id": order_id,
                "reason": reason,
                "legal": legal_basis,
                "version": policy_version,
                "at": requested_at,
            },
        )

    def refund_status(self, customer_unique_id: str, order_id: str) -> str | None:
        with self.pool.connection() as conn:
            row = conn.execute(
                _OWNED
                + sql.SQL("""
                SELECT r.refund_status FROM sim.refund_requests r JOIN owned USING (order_id)
                ORDER BY r.requested_at DESC, r.request_id DESC LIMIT 1
                """),
                {"customer": customer_unique_id, "order_id": order_id},
            ).fetchone()
        return row[0] if row else None

    def customer_tickets(self, customer_unique_id: str) -> list[TicketRow]:
        with self.pool.connection() as conn, conn.cursor(row_factory=class_row(TicketRow)) as cur:
            cur.execute(
                "SELECT ticket_type, ticket_status, ticket_opened_at FROM sim.tickets "
                "WHERE customer_unique_id = %s ORDER BY ticket_opened_at",
                (customer_unique_id,),
            )
            return cur.fetchall()

    def _one(self, query: sql.Composable, params: dict) -> int | None:
        with self.pool.connection() as conn:
            row = conn.execute(query, params).fetchone()
        return row[0] if row else None

    def ping(self) -> None:
        with self.pool.connection() as conn:
            conn.execute("SELECT 1")


# Filtro comum das buscas: lei sempre; política só na versão vigente no dia informado (decisão D3);
# com intenções, só as políticas delas e as transversais (intents vazio).
_KB_FILTER = sql.SQL("""
    (source_type = 'legal_public_source'
     OR (effective_from <= %(day)s AND (effective_until IS NULL OR %(day)s <= effective_until)))
    AND (%(intents)s::text[] IS NULL OR intents && %(intents)s::text[] OR intents = '{}')
""")
_KB_COLUMNS = sql.SQL("chunk_id, doc_id, version, source_type, title, escalation, text")


class PostgresKnowledgeRepository:
    def __init__(self, pool: ConnectionPool) -> None:
        self.pool = pool

    def lexical(self, query: str, day: date, intents: list[str] | None, k: int) -> list[ChunkRow]:
        # Termos ligados por OU: com E, mensagens longas de cliente não casariam com nada
        stmt = sql.SQL("""
            WITH q AS (SELECT replace(plainto_tsquery('portuguese', %(query)s)::text, '&', '|') AS t)
            SELECT {cols} FROM kb.chunks, q
            WHERE q.t <> '' AND tsv @@ q.t::tsquery AND {filter}
            ORDER BY ts_rank_cd(tsv, q.t::tsquery) DESC, chunk_id
            LIMIT %(k)s
        """).format(cols=_KB_COLUMNS, filter=_KB_FILTER)
        return self._fetch(stmt, {"query": query, "day": day, "intents": intents, "k": k})

    def vector(self, embedding: list[float], day: date, intents: list[str] | None, k: int) -> list[ChunkRow]:
        stmt = sql.SQL("""
            SELECT {cols} FROM kb.chunks
            WHERE embedding IS NOT NULL AND {filter}
            ORDER BY embedding <=> %(embedding)s::vector, chunk_id
            LIMIT %(k)s
        """).format(cols=_KB_COLUMNS, filter=_KB_FILTER)
        params = {"embedding": str(embedding), "day": day, "intents": intents, "k": k}
        return self._fetch(stmt, params)

    def get_chunks(self, chunk_ids: list[str]) -> list[ChunkRow]:
        stmt = sql.SQL("SELECT {} FROM kb.chunks WHERE chunk_id = ANY(%(ids)s) ORDER BY chunk_id").format(
            _KB_COLUMNS
        )
        return self._fetch(stmt, {"ids": chunk_ids})

    def _fetch(self, query: sql.Composable, params: dict) -> list[ChunkRow]:
        with self.pool.connection() as conn, conn.cursor(row_factory=class_row(ChunkRow)) as cur:
            cur.execute(query, params)
            return cur.fetchall()
