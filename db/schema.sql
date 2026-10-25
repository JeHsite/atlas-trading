-- Atlas schema (PostgreSQL + TimescaleDB)
CREATE EXTENSION IF NOT EXISTS timescaledb;

CREATE TABLE instruments (
    symbol       TEXT PRIMARY KEY,
    asset_class  TEXT NOT NULL CHECK (asset_class IN ('equity','etf','bond','crypto','fx')),
    venue        TEXT NOT NULL,
    currency     CHAR(3) NOT NULL,
    country      CHAR(2),
    sector       TEXT,
    active       BOOLEAN NOT NULL DEFAULT TRUE
);

CREATE TABLE bars (
    symbol     TEXT NOT NULL REFERENCES instruments(symbol),
    timeframe  TEXT NOT NULL,
    ts         TIMESTAMPTZ NOT NULL,
    open       DOUBLE PRECISION NOT NULL,
    high       DOUBLE PRECISION NOT NULL,
    low        DOUBLE PRECISION NOT NULL,
    close      DOUBLE PRECISION NOT NULL,
    volume     DOUBLE PRECISION NOT NULL,
    PRIMARY KEY (symbol, timeframe, ts)
);
SELECT create_hypertable('bars', 'ts', if_not_exists => TRUE);

-- News, filings, transcripts, speeches, macro releases (untrusted text)
CREATE TABLE documents (
    id            TEXT PRIMARY KEY,
    kind          TEXT NOT NULL,
    source        TEXT NOT NULL,
    published_at  TIMESTAMPTZ NOT NULL,
    title         TEXT NOT NULL,
    body          TEXT NOT NULL,
    url           TEXT,
    symbols       TEXT[] NOT NULL DEFAULT '{}'
);
CREATE INDEX documents_published_idx ON documents (published_at DESC);

-- Structured model output about a document (classification, scores, summary)
CREATE TABLE document_analyses (
    document_id  TEXT NOT NULL REFERENCES documents(id),
    model        TEXT NOT NULL,
    analysis     JSONB NOT NULL,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (document_id, model)
);

-- Every model call, for cost control and audit
CREATE TABLE llm_calls (
    id                  BIGSERIAL PRIMARY KEY,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    task                TEXT NOT NULL,
    model               TEXT NOT NULL,
    input_tokens        INTEGER NOT NULL,
    cache_read_tokens   INTEGER NOT NULL DEFAULT 0,
    cache_write_tokens  INTEGER NOT NULL DEFAULT 0,
    output_tokens       INTEGER NOT NULL,
    cost_usd            NUMERIC(12, 6) NOT NULL,
    stop_reason         TEXT,
    request_id          TEXT
);
CREATE INDEX llm_calls_day_idx ON llm_calls (created_at);

CREATE TABLE trade_proposals (
    id           BIGSERIAL PRIMARY KEY,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    symbol       TEXT NOT NULL REFERENCES instruments(symbol),
    direction    TEXT NOT NULL CHECK (direction IN ('long','short')),
    horizon      TEXT NOT NULL,
    setup        TEXT NOT NULL DEFAULT 'discretionary',
    proposal     JSONB NOT NULL,
    llm_call_id  BIGINT REFERENCES llm_calls(id)
);

CREATE TABLE risk_decisions (
    proposal_id      BIGINT PRIMARY KEY REFERENCES trade_proposals(id),
    created_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
    approved         BOOLEAN NOT NULL,
    quantity         DOUBLE PRECISION NOT NULL,
    order_value_base DOUBLE PRECISION NOT NULL,
    rejections       TEXT[] NOT NULL DEFAULT '{}',
    adjustments      TEXT[] NOT NULL DEFAULT '{}',
    limits_snapshot  JSONB NOT NULL
);

CREATE TABLE orders (
    id            BIGSERIAL PRIMARY KEY,
    proposal_id   BIGINT NOT NULL REFERENCES risk_decisions(proposal_id),
    broker        TEXT NOT NULL,
    broker_ref    TEXT,
    mode          TEXT NOT NULL CHECK (mode IN ('paper','live')),
    side          TEXT NOT NULL CHECK (side IN ('buy','sell')),
    quantity      DOUBLE PRECISION NOT NULL,
    order_type    TEXT NOT NULL,
    limit_price   DOUBLE PRECISION,
    stop_price    DOUBLE PRECISION,
    status        TEXT NOT NULL,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE fills (
    id         BIGSERIAL PRIMARY KEY,
    order_id   BIGINT NOT NULL REFERENCES orders(id),
    ts         TIMESTAMPTZ NOT NULL,
    quantity   DOUBLE PRECISION NOT NULL,
    price      DOUBLE PRECISION NOT NULL,
    fee_base   DOUBLE PRECISION NOT NULL DEFAULT 0
);

-- Closed trades, for win rate / expectancy / R-multiple statistics
CREATE TABLE trade_results (
    proposal_id   BIGINT PRIMARY KEY REFERENCES trade_proposals(id),
    opened_at     TIMESTAMPTZ NOT NULL,
    closed_at     TIMESTAMPTZ NOT NULL,
    pnl_base      DOUBLE PRECISION NOT NULL,
    r_multiple    DOUBLE PRECISION NOT NULL,
    exit_reason   TEXT NOT NULL
);

CREATE TABLE equity_snapshots (
    ts          TIMESTAMPTZ PRIMARY KEY,
    equity_base DOUBLE PRECISION NOT NULL,
    positions   JSONB NOT NULL
);

-- Learning layer: one post-mortem per closed trade
CREATE TABLE trade_reviews (
    proposal_id     BIGINT PRIMARY KEY REFERENCES trade_results(proposal_id),
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    setup           TEXT NOT NULL,
    asset_class     TEXT NOT NULL,
    thesis_correct  TEXT NOT NULL CHECK (thesis_correct IN ('yes','partly','no')),
    mistake         TEXT NOT NULL,
    lesson          TEXT NOT NULL CHECK (length(lesson) <= 300),
    llm_call_id     BIGINT REFERENCES llm_calls(id)
);

-- Per-domain track record (setup x asset class)
CREATE VIEW setup_stats AS
SELECT p.setup,
       i.asset_class,
       count(*)                                         AS trades,
       avg((r.pnl_base > 0)::int)                       AS win_rate,
       avg(r.r_multiple)                                AS avg_r,
       sum(r.r_multiple) / (count(*) + 20)              AS shrunk_r
FROM trade_results r
JOIN trade_proposals p ON p.id = r.proposal_id
JOIN instruments i ON i.symbol = p.symbol
GROUP BY p.setup, i.asset_class;
