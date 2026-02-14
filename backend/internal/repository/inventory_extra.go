package repository

import (
	"context"
	"database/sql"
	"fmt"
	"strings"

	"backend/internal/domain"
)

func (r *Repository) ReplaceInventory(ctx context.Context, rows []domain.InventoryImportRow) error {
	tx, err := r.pool.Begin(ctx)
	if err != nil {
		return fmt.Errorf("begin replace inventory tx: %w", err)
	}
	defer tx.Rollback(ctx)

	if _, err := tx.Exec(ctx, "DELETE FROM products"); err != nil {
		return fmt.Errorf("clear products: %w", err)
	}

	for _, line := range rows {
		name := strings.TrimSpace(line.ProductName)
		if name == "" {
			continue
		}
		if _, err := tx.Exec(ctx, `
			INSERT INTO products (
				product_name,
				quantity,
				avg_buy_price,
				last_buy_price,
				sell_price,
				alarm,
				source
			) VALUES ($1, $2, $3, $4, $5, $6, $7)
		`,
			name,
			line.Quantity,
			line.AvgBuyPrice,
			line.LastBuyPrice,
			line.SellPrice,
			line.Alarm,
			line.Source,
		); err != nil {
			return fmt.Errorf("insert product %q during replace: %w", name, err)
		}
	}

	if err := tx.Commit(ctx); err != nil {
		return fmt.Errorf("commit replace inventory tx: %w", err)
	}
	return nil
}

func (r *Repository) ListAllProducts(ctx context.Context) ([]domain.Product, error) {
	rows, err := r.pool.Query(ctx, `
		SELECT
			id,
			product_name,
			quantity,
			avg_buy_price::double precision,
			last_buy_price::double precision,
			sell_price::double precision,
			alarm,
			source,
			created_at,
			updated_at
		FROM products
		ORDER BY id ASC
	`)
	if err != nil {
		return nil, fmt.Errorf("list all products: %w", err)
	}
	defer rows.Close()

	items := make([]domain.Product, 0)
	for rows.Next() {
		item, err := scanProduct(rows)
		if err != nil {
			return nil, err
		}
		items = append(items, item)
	}
	if err := rows.Err(); err != nil {
		return nil, fmt.Errorf("iterate all products: %w", err)
	}
	return items, nil
}

func (r *Repository) GetLowStock(ctx context.Context, threshold int) ([]domain.LowStockRow, error) {
	if threshold <= 0 {
		threshold = 5
	}
	rows, err := r.pool.Query(ctx, `
		SELECT
			product_name,
			quantity,
			COALESCE(alarm, $1) AS alarm,
			(COALESCE(alarm, $1) - quantity) AS needed,
			avg_buy_price::double precision,
			sell_price::double precision,
			source
		FROM products
		WHERE quantity < COALESCE(alarm, $1)
		ORDER BY needed DESC, product_name ASC
	`, threshold)
	if err != nil {
		return nil, fmt.Errorf("get low stock: %w", err)
	}
	defer rows.Close()

	result := make([]domain.LowStockRow, 0)
	for rows.Next() {
		var (
			row    domain.LowStockRow
			source sql.NullString
		)
		if err := rows.Scan(
			&row.ProductName,
			&row.Quantity,
			&row.Alarm,
			&row.Needed,
			&row.AvgBuyPrice,
			&row.SellPrice,
			&source,
		); err != nil {
			return nil, fmt.Errorf("scan low stock row: %w", err)
		}
		if source.Valid {
			value := source.String
			row.Source = &value
		}
		result = append(result, row)
	}
	if err := rows.Err(); err != nil {
		return nil, fmt.Errorf("iterate low stock rows: %w", err)
	}
	return result, nil
}
