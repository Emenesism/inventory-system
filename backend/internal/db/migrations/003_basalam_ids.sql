CREATE TABLE IF NOT EXISTS basalam_order_ids (
    id TEXT PRIMARY KEY,
    saved_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_basalam_order_ids_saved_at
    ON basalam_order_ids(saved_at);
