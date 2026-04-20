CREATE TABLE IF NOT EXISTS product_groups (
    id BIGSERIAL PRIMARY KEY,
    name TEXT NOT NULL,
    name_normalized TEXT GENERATED ALWAYS AS (LOWER(name)) STORED,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_product_groups_name_normalized UNIQUE (name_normalized)
);

CREATE TABLE IF NOT EXISTS product_group_members (
    group_id BIGINT NOT NULL REFERENCES product_groups(id) ON DELETE CASCADE,
    product_id BIGINT NOT NULL REFERENCES products(id) ON DELETE CASCADE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (group_id, product_id),
    CONSTRAINT uq_product_group_members_product UNIQUE (product_id)
);

CREATE INDEX IF NOT EXISTS idx_product_group_members_group_id
    ON product_group_members (group_id);

CREATE TABLE IF NOT EXISTS invoice_stock_effects (
    invoice_id BIGINT NOT NULL REFERENCES invoices(id) ON DELETE CASCADE,
    product_id BIGINT NOT NULL,
    product_name TEXT NOT NULL,
    quantity INTEGER NOT NULL,
    total_cost NUMERIC(14,4) NOT NULL DEFAULT 0,
    last_price NUMERIC(14,4) NOT NULL DEFAULT 0,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (invoice_id, product_id)
);

CREATE INDEX IF NOT EXISTS idx_invoice_stock_effects_invoice_id
    ON invoice_stock_effects (invoice_id);
