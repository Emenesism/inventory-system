package repository

import (
	"context"
	"database/sql"
	"fmt"
	"sort"
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

func (r *Repository) ImportSellPrices(
	ctx context.Context,
	rows []domain.ProductPriceRow,
) (domain.SellPriceImportResult, error) {
	result := domain.SellPriceImportResult{TotalRows: len(rows)}
	if len(rows) == 0 {
		return result, fmt.Errorf("price rows are required")
	}

	tx, err := r.pool.Begin(ctx)
	if err != nil {
		return result, fmt.Errorf("begin sell price import tx: %w", err)
	}
	defer tx.Rollback(ctx)

	productsRows, err := tx.Query(ctx, `
		SELECT id, product_name
		FROM products
	`)
	if err != nil {
		return result, fmt.Errorf("query products for sell price import: %w", err)
	}
	defer productsRows.Close()

	exactMap := make(map[string]int64)
	normalizedMap := make(map[string]int64)
	for productsRows.Next() {
		var (
			id   int64
			name string
		)
		if scanErr := productsRows.Scan(&id, &name); scanErr != nil {
			return result, fmt.Errorf("scan product during sell price import: %w", scanErr)
		}
		exactKey := strings.ToLower(strings.TrimSpace(name))
		if exactKey != "" {
			if _, exists := exactMap[exactKey]; !exists {
				exactMap[exactKey] = id
			}
		}
		normalizedKey := normalizeSellPriceLookupName(name)
		if normalizedKey != "" {
			if _, exists := normalizedMap[normalizedKey]; !exists {
				normalizedMap[normalizedKey] = id
			}
		}
	}
	if err := productsRows.Err(); err != nil {
		return result, fmt.Errorf("iterate products for sell price import: %w", err)
	}

	unmatchedSet := make(map[string]struct{})
	priceByProductID := make(map[int64]float64)
	for _, row := range rows {
		name := strings.TrimSpace(row.ProductName)
		if name == "" {
			continue
		}
		if row.Price < 0 {
			return result, fmt.Errorf("invalid price for %q", name)
		}

		exactKey := strings.ToLower(name)
		productID, ok := exactMap[exactKey]
		if !ok {
			productID, ok = normalizedMap[normalizeSellPriceLookupName(name)]
		}
		if !ok {
			unmatchedSet[name] = struct{}{}
			continue
		}
		result.MatchedRows++
		priceByProductID[productID] = row.Price
	}

	for productID, price := range priceByProductID {
		if _, err := tx.Exec(ctx, `
			UPDATE products
			SET
				sell_price = $2,
				updated_at = NOW()
			WHERE id = $1
		`, productID, price); err != nil {
			return result, fmt.Errorf("update sell price for product %d: %w", productID, err)
		}
	}

	result.UpdatedProducts = len(priceByProductID)
	if len(unmatchedSet) > 0 {
		unmatched := make([]string, 0, len(unmatchedSet))
		for name := range unmatchedSet {
			unmatched = append(unmatched, name)
		}
		sort.Strings(unmatched)
		result.UnmatchedCount = len(unmatched)
		if len(unmatched) > 50 {
			unmatched = unmatched[:50]
		}
		result.UnmatchedNames = unmatched
	}

	if err := tx.Commit(ctx); err != nil {
		return result, fmt.Errorf("commit sell price import tx: %w", err)
	}
	return result, nil
}

func normalizeSellPriceLookupName(value string) string {
	if value == "" {
		return ""
	}
	replaced := strings.NewReplacer(
		"ي", "ی",
		"ك", "ک",
		"ة", "ه",
		"ۀ", "ه",
		"ؤ", "و",
		"أ", "ا",
		"إ", "ا",
		"ٱ", "ا",
		"آ", "ا",
		"ئ", "ی",
		"۰", "0",
		"۱", "1",
		"۲", "2",
		"۳", "3",
		"۴", "4",
		"۵", "5",
		"۶", "6",
		"۷", "7",
		"۸", "8",
		"۹", "9",
		"٠", "0",
		"١", "1",
		"٢", "2",
		"٣", "3",
		"٤", "4",
		"٥", "5",
		"٦", "6",
		"٧", "7",
		"٨", "8",
		"٩", "9",
		"٬", "",
		",", " ",
		"،", " ",
		"؛", " ",
		";", " ",
		":", " ",
		".", " ",
		"ـ", " ",
		"‌", " ",
		"\u200c", " ",
		"\u200d", " ",
	)
	normalized := replaced.Replace(value)
	normalized = strings.Join(strings.Fields(normalized), " ")
	return strings.ToLower(strings.TrimSpace(normalized))
}
