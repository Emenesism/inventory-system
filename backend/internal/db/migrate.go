package db

import (
	"context"
	"embed"
	"fmt"
	"io/fs"
	"sort"
	"strings"

	"github.com/jackc/pgx/v5/pgxpool"
)

//go:embed migrations/*.sql
var migrationFiles embed.FS

func RunMigrations(ctx context.Context, pool *pgxpool.Pool) error {
	if _, err := pool.Exec(ctx, `
		CREATE TABLE IF NOT EXISTS schema_migrations (
			version TEXT PRIMARY KEY,
			applied_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
		)
	`); err != nil {
		return fmt.Errorf("create schema_migrations table: %w", err)
	}

	if err := ensureCoreSchema(ctx, pool); err != nil {
		return err
	}

	entries, err := fs.ReadDir(migrationFiles, "migrations")
	if err != nil {
		return fmt.Errorf("read embedded migrations: %w", err)
	}

	versions := make([]string, 0, len(entries))
	for _, entry := range entries {
		if entry.IsDir() || !strings.HasSuffix(entry.Name(), ".sql") {
			continue
		}
		versions = append(versions, entry.Name())
	}
	sort.Strings(versions)

	for _, version := range versions {
		var exists bool
		if err := pool.QueryRow(ctx,
			"SELECT EXISTS(SELECT 1 FROM schema_migrations WHERE version = $1)",
			version,
		).Scan(&exists); err != nil {
			return fmt.Errorf("check migration %s: %w", version, err)
		}
		if exists {
			continue
		}

		body, err := migrationFiles.ReadFile("migrations/" + version)
		if err != nil {
			return fmt.Errorf("read migration %s: %w", version, err)
		}

		tx, err := pool.Begin(ctx)
		if err != nil {
			return fmt.Errorf("begin migration tx %s: %w", version, err)
		}

		if _, err := tx.Exec(ctx, string(body)); err != nil {
			_ = tx.Rollback(ctx)
			return fmt.Errorf("apply migration %s: %w", version, err)
		}
		if _, err := tx.Exec(ctx,
			"INSERT INTO schema_migrations(version) VALUES($1)",
			version,
		); err != nil {
			_ = tx.Rollback(ctx)
			return fmt.Errorf("record migration %s: %w", version, err)
		}
		if err := tx.Commit(ctx); err != nil {
			return fmt.Errorf("commit migration %s: %w", version, err)
		}
	}

	if err := ensureCoreSchema(ctx, pool); err != nil {
		return err
	}

	return nil
}

func ensureCoreSchema(ctx context.Context, pool *pgxpool.Pool) error {
	steps := []struct {
		name string
		sql  string
	}{
		{
			name: "products table",
			sql: `
				CREATE TABLE IF NOT EXISTS products (
					id BIGSERIAL PRIMARY KEY,
					product_name TEXT NOT NULL,
					product_name_normalized TEXT GENERATED ALWAYS AS (LOWER(product_name)) STORED,
					quantity INTEGER NOT NULL DEFAULT 0,
					avg_buy_price NUMERIC(14,4) NOT NULL DEFAULT 0,
					last_buy_price NUMERIC(14,4) NOT NULL DEFAULT 0,
					sell_price NUMERIC(14,4) NOT NULL DEFAULT 0,
					alarm INTEGER,
					source TEXT,
					created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
					updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
					CONSTRAINT uq_products_name_normalized UNIQUE (product_name_normalized)
				)
			`,
		},
		{
			name: "invoices table",
			sql: `
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
				)
			`,
		},
		{
			name: "invoice_lines table",
			sql: `
				CREATE TABLE IF NOT EXISTS invoice_lines (
					id BIGSERIAL PRIMARY KEY,
					invoice_id BIGINT NOT NULL REFERENCES invoices(id) ON DELETE CASCADE,
					product_name TEXT NOT NULL,
					price NUMERIC(14,4) NOT NULL,
					quantity INTEGER NOT NULL,
					line_total NUMERIC(14,4) NOT NULL,
					cost_price NUMERIC(14,4) NOT NULL DEFAULT 0
				)
			`,
		},
		{
			name: "actions table",
			sql: `
				CREATE TABLE IF NOT EXISTS actions (
					id BIGSERIAL PRIMARY KEY,
					created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
					admin_username TEXT,
					action_type TEXT NOT NULL,
					title TEXT NOT NULL,
					details TEXT NOT NULL
				)
			`,
		},
		{
			name: "admins table",
			sql: `
				CREATE TABLE IF NOT EXISTS admins (
					id BIGSERIAL PRIMARY KEY,
					username TEXT NOT NULL UNIQUE,
					password TEXT NOT NULL,
					role TEXT NOT NULL,
					auto_lock_minutes INTEGER NOT NULL DEFAULT 1,
					created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
				)
			`,
		},
		{
			name: "basalam_order_ids table",
			sql: `
				CREATE TABLE IF NOT EXISTS basalam_order_ids (
					id TEXT PRIMARY KEY,
					saved_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
				)
			`,
		},
		{
			name: "stock table",
			sql: `
				CREATE TABLE IF NOT EXISTS stock (
					id BIGSERIAL PRIMARY KEY,
					product_name TEXT NOT NULL,
					product_name_normalized TEXT GENERATED ALWAYS AS (LOWER(product_name)) STORED,
					quantity INTEGER NOT NULL DEFAULT 0,
					avg_buy_price NUMERIC(14,4) NOT NULL DEFAULT 0,
					last_buy_price NUMERIC(14,4) NOT NULL DEFAULT 0,
					sell_price NUMERIC(14,4) NOT NULL DEFAULT 0,
					alarm INTEGER,
					source TEXT,
					imported_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
					updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
					CONSTRAINT uq_stock_name_normalized UNIQUE (product_name_normalized)
				)
			`,
		},
		{
			name: "app_settings table",
			sql: `
				CREATE TABLE IF NOT EXISTS app_settings (
					key TEXT PRIMARY KEY,
					value_numeric NUMERIC(14,4) NOT NULL,
					updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
				)
			`,
		},
		{
			name: "default sell price alarm setting",
			sql: `
				INSERT INTO app_settings (key, value_numeric)
				VALUES ('sell_price_alarm_percent', 20)
				ON CONFLICT (key) DO NOTHING
			`,
		},
		{
			name: "products quantity index",
			sql:  `CREATE INDEX IF NOT EXISTS idx_products_quantity ON products (quantity)`,
		},
		{
			name: "invoices created_at index",
			sql:  `CREATE INDEX IF NOT EXISTS idx_invoices_created_at ON invoices (created_at DESC)`,
		},
		{
			name: "invoices type index",
			sql:  `CREATE INDEX IF NOT EXISTS idx_invoices_type ON invoices (invoice_type)`,
		},
		{
			name: "invoice_lines invoice_id index",
			sql:  `CREATE INDEX IF NOT EXISTS idx_invoice_lines_invoice_id ON invoice_lines (invoice_id)`,
		},
		{
			name: "actions created_at index",
			sql:  `CREATE INDEX IF NOT EXISTS idx_actions_created_at ON actions (created_at DESC)`,
		},
		{
			name: "actions type index",
			sql:  `CREATE INDEX IF NOT EXISTS idx_actions_type ON actions (action_type)`,
		},
		{
			name: "admins username index",
			sql:  `CREATE INDEX IF NOT EXISTS idx_admins_username ON admins (username)`,
		},
		{
			name: "basalam ids saved_at index",
			sql:  `CREATE INDEX IF NOT EXISTS idx_basalam_order_ids_saved_at ON basalam_order_ids(saved_at)`,
		},
		{
			name: "stock quantity index",
			sql:  `CREATE INDEX IF NOT EXISTS idx_stock_quantity ON stock (quantity)`,
		},
		{
			name: "products.sell_price column",
			sql: `
				ALTER TABLE products
				ADD COLUMN IF NOT EXISTS sell_price NUMERIC(14,4) NOT NULL DEFAULT 0
			`,
		},
		{
			name: "stock.sell_price column",
			sql: `
				ALTER TABLE stock
				ADD COLUMN IF NOT EXISTS sell_price NUMERIC(14,4) NOT NULL DEFAULT 0
			`,
		},
	}

	for _, step := range steps {
		if _, err := pool.Exec(ctx, step.sql); err != nil {
			return fmt.Errorf("ensure %s: %w", step.name, err)
		}
	}

	return nil
}
