-- Schemas do CommerceOps AI
--   olist : dados históricos reais do dataset (somente leitura para a aplicação)
--   sim   : dados operacionais SIMULADOS (ocorrências, cancelamentos, devoluções, reembolsos)
--   kb    : base de conhecimento indexada (políticas fictícias + fontes legais)
-- A separação física entre real e simulado é a decisão D6 (docs/01_politicas_v1.1.md).

CREATE EXTENSION IF NOT EXISTS vector;

CREATE SCHEMA olist;
CREATE SCHEMA sim;
CREATE SCHEMA kb;

COMMENT ON SCHEMA olist IS 'Dados reais do Brazilian E-Commerce Public Dataset by Olist (2016-2018). Somente leitura.';
COMMENT ON SCHEMA sim IS 'Dados SIMULADOS do ambiente de atendimento. Nada aqui é registro real da Olist.';
COMMENT ON SCHEMA kb IS 'Base de conhecimento: políticas fictícias e textos legais públicos.';

-- ---------------------------------------------------------------- olist
-- Prefixos de CEP são TEXTO: o CSV tem zero à esquerda ("09790").

CREATE TABLE olist.customers (
    customer_id              text PRIMARY KEY,   -- único POR PEDIDO, não identifica a pessoa
    customer_unique_id       text NOT NULL,      -- identifica a pessoa
    customer_zip_code_prefix char(5) NOT NULL,
    customer_city            text NOT NULL,
    customer_state           char(2) NOT NULL
);
CREATE INDEX ON olist.customers (customer_unique_id);

CREATE TABLE olist.sellers (
    seller_id              text PRIMARY KEY,
    seller_zip_code_prefix char(5) NOT NULL,
    seller_city            text NOT NULL,
    seller_state           char(2) NOT NULL
);

CREATE TABLE olist.category_translation (
    product_category_name         text PRIMARY KEY,
    product_category_name_english text NOT NULL
);

CREATE TABLE olist.products (
    product_id                 text PRIMARY KEY,
    product_category_name      text,
    product_name_length        integer,   -- "lenght" no CSV original
    product_description_length integer,   -- "lenght" no CSV original
    product_photos_qty         integer,
    product_weight_g           integer,
    product_length_cm          integer,
    product_height_cm          integer,
    product_width_cm           integer
);

CREATE TABLE olist.orders (
    order_id                      text PRIMARY KEY,
    customer_id                   text NOT NULL REFERENCES olist.customers,
    order_status                  text NOT NULL,
    order_purchase_timestamp      timestamp NOT NULL,
    order_approved_at             timestamp,
    order_delivered_carrier_date  timestamp,
    order_delivered_customer_date timestamp,
    order_estimated_delivery_date date NOT NULL   -- sempre meia-noite no CSV
);
CREATE INDEX ON olist.orders (customer_id);

CREATE TABLE olist.order_items (
    order_id            text NOT NULL REFERENCES olist.orders,
    order_item_id       integer NOT NULL,
    product_id          text NOT NULL REFERENCES olist.products,
    seller_id           text NOT NULL REFERENCES olist.sellers,
    shipping_limit_date timestamp NOT NULL,
    price               numeric(10, 2) NOT NULL,
    freight_value       numeric(10, 2) NOT NULL,
    PRIMARY KEY (order_id, order_item_id)
);

CREATE TABLE olist.order_payments (
    order_id             text NOT NULL REFERENCES olist.orders,
    payment_sequential   integer NOT NULL,
    payment_type         text NOT NULL,
    payment_installments integer NOT NULL,
    payment_value        numeric(10, 2) NOT NULL,
    PRIMARY KEY (order_id, payment_sequential)
);

CREATE TABLE olist.order_reviews (
    review_row_id           integer PRIMARY KEY,   -- chave técnica: review_id NÃO é único
    review_id               text NOT NULL,
    order_id                text NOT NULL REFERENCES olist.orders,
    review_score            smallint NOT NULL CHECK (review_score BETWEEN 1 AND 5),
    review_comment_title    text,
    review_comment_message  text,
    review_creation_date    date NOT NULL,          -- só data: resíduo de fuso descartado
    review_answer_timestamp timestamp NOT NULL,
    review_id_duplicate     boolean NOT NULL
);
CREATE INDEX ON olist.order_reviews (order_id);

-- ---------------------------------------------------------------- sim

CREATE TABLE sim.tickets (
    ticket_id         bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    scenario_id       text,                       -- cenário de avaliação que gerou a ocorrência
    order_id          text NOT NULL REFERENCES olist.orders,
    customer_unique_id text NOT NULL,
    ticket_type       text NOT NULL CHECK (ticket_type IN (
        'atraso_entrega', 'expedicao_atrasada', 'investigacao_entrega', 'divergencia_produto',
        'defeito_produto', 'cobranca', 'reclamacao_atendimento', 'outro')),
    ticket_status     text NOT NULL DEFAULT 'aberto'
        CHECK (ticket_status IN ('aberto', 'em_analise', 'aguardando_cliente', 'resolvido', 'encerrado')),
    escalated         boolean NOT NULL DEFAULT false,
    policy_ids        text[] NOT NULL DEFAULT '{}',
    ticket_opened_at  timestamp NOT NULL,         -- data de referência do cenário, não o relógio
    created_at        timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX ON sim.tickets (customer_unique_id);
-- Idempotência: repetir a mensagem não abre outra ocorrência do mesmo tipo enquanto houver uma aberta
CREATE UNIQUE INDEX ON sim.tickets (order_id, ticket_type)
    WHERE ticket_status NOT IN ('resolvido', 'encerrado');

CREATE TABLE sim.cancellation_requests (
    request_id     bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    order_id       text NOT NULL REFERENCES olist.orders,
    status         text NOT NULL DEFAULT 'solicitado'
        CHECK (status IN ('solicitado', 'concluido', 'recusado')),
    requested_at   timestamp NOT NULL
);
CREATE UNIQUE INDEX ON sim.cancellation_requests (order_id) WHERE status = 'solicitado';

CREATE TABLE sim.return_requests (
    request_id     bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    order_id       text NOT NULL REFERENCES olist.orders,
    reason         text NOT NULL CHECK (reason IN ('arrependimento', 'defeito', 'divergencia')),
    legal_basis    text,                          -- ex.: LEG-CDC-049 quando dentro de 7 dias
    policy_version text NOT NULL,                 -- versão da POL-DEV-001 aplicada
    status         text NOT NULL DEFAULT 'solicitado'
        CHECK (status IN ('solicitado', 'em_analise', 'aprovado', 'recusado', 'concluido')),
    requested_at   timestamp NOT NULL
);
CREATE UNIQUE INDEX ON sim.return_requests (order_id) WHERE status IN ('solicitado', 'em_analise');

CREATE TABLE sim.refund_requests (
    request_id     bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    order_id       text NOT NULL REFERENCES olist.orders,
    amount         numeric(10, 2) NOT NULL CHECK (amount > 0),
    refund_status  text NOT NULL DEFAULT 'solicitado'
        CHECK (refund_status IN ('solicitado', 'em_analise', 'aprovado', 'processado', 'nao_elegivel')),
    requires_human_approval boolean NOT NULL,     -- POL-REF-001-S03: > R$ 1.000,00
    requested_at   timestamp NOT NULL
);

-- Trilha de auditoria de toda ação de ferramenta do agente (inclusive as recusadas).
CREATE TABLE sim.agent_actions (
    action_id      bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    trace_id       text,                          -- liga ao trace do Langfuse
    tool_name      text NOT NULL,
    order_id_hash  text,                          -- HMAC, nunca o order_id cru
    allowed        boolean NOT NULL,
    reason         text,
    created_at     timestamptz NOT NULL DEFAULT now()
);

-- ---------------------------------------------------------------- kb

CREATE TABLE kb.chunks (
    chunk_id        text PRIMARY KEY,             -- section_id@version ou legal_id
    doc_id          text NOT NULL,
    version         text,
    source_type     text NOT NULL CHECK (source_type IN ('fictional_policy', 'legal_public_source')),
    fictional       boolean NOT NULL,
    title           text NOT NULL,
    effective_from  date,
    effective_until date,
    intents         text[] NOT NULL DEFAULT '{}',
    escalation      text NOT NULL,
    text            text NOT NULL,
    tsv             tsvector GENERATED ALWAYS AS (
                        to_tsvector('portuguese', title || ' ' || text)) STORED,
    embedding       vector(1024),                 -- bge-m3; preenchido na etapa de RAG
    embedding_model text
);
CREATE INDEX ON kb.chunks USING gin (tsv);
-- Índice HNSW fica para depois: com ~50 chunks, a busca exata é a referência de qualidade.
-- Privilégios do usuário da aplicação: ver 02_app_role.sh.
