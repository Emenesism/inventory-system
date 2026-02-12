CREATE TABLE IF NOT EXISTS products (
    id BIGSERIAL PRIMARY KEY,
    product_name TEXT NOT NULL,
    product_name_normalized TEXT GENERATED ALWAYS AS (LOWER(product_name)) STORED,
    quantity INTEGER NOT NULL DEFAULT 0,
    avg_buy_price NUMERIC(14,4) NOT NULL DEFAULT 0,
    last_buy_price NUMERIC(14,4) NOT NULL DEFAULT 0,
    alarm INTEGER,
    source TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_products_name_normalized UNIQUE (product_name_normalized)
);

CREATE INDEX IF NOT EXISTS idx_products_quantity ON products (quantity);

CREATE TABLE IF NOT EXISTS invoices (
    id BIGSERIAL PRIMARY KEY,
    invoice_type TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    total_lines INTEGER NOT NULL,
    total_qty INTEGER NOT NULL,
    total_amount NUMERIC(14,4) NOT NULL,
    invoice_name TEXT,
    admin_username TEXT,
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb
);

CREATE INDEX IF NOT EXISTS idx_invoices_created_at ON invoices (created_at DESC);
CREATE INDEX IF NOT EXISTS idx_invoices_type ON invoices (invoice_type);

CREATE TABLE IF NOT EXISTS invoice_lines (
    id BIGSERIAL PRIMARY KEY,
    invoice_id BIGINT NOT NULL REFERENCES invoices(id) ON DELETE CASCADE,
    product_name TEXT NOT NULL,
    price NUMERIC(14,4) NOT NULL,
    quantity INTEGER NOT NULL,
    line_total NUMERIC(14,4) NOT NULL,
    cost_price NUMERIC(14,4) NOT NULL DEFAULT 0
);

CREATE INDEX IF NOT EXISTS idx_invoice_lines_invoice_id ON invoice_lines (invoice_id);

CREATE TABLE IF NOT EXISTS actions (
    id BIGSERIAL PRIMARY KEY,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    admin_username TEXT,
    action_type TEXT NOT NULL,
    title TEXT NOT NULL,
    details TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_actions_created_at ON actions (created_at DESC);
CREATE INDEX IF NOT EXISTS idx_actions_type ON actions (action_type);

CREATE TABLE IF NOT EXISTS schema_migrations (
    version TEXT PRIMARY KEY,
    applied_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
