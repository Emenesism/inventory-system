package repository

import (
	"context"
	"database/sql"
	"errors"
	"fmt"
	"strings"
	"time"

	"backend/internal/domain"

	"github.com/jackc/pgx/v5"
	"github.com/jackc/pgx/v5/pgxpool"
)

var ErrNotFound = errors.New("not found")

type ProductListFilter struct {
	Search    string
	Limit     int
	Offset    int
	Threshold *int
}

type ProductCreateInput struct {
	ProductName  string
	Quantity     int
	AvgBuyPrice  float64
	LastBuyPrice float64
	Alarm        *int
	Source       *string
}

type ProductPatchInput struct {
	ProductName  *string
	Quantity     *int
	AvgBuyPrice  *float64
	LastBuyPrice *float64
	Alarm        *int
	Source       *string
}

type InventorySummary struct {
	TotalProducts  int     `json:"total_products"`
	TotalQuantity  int     `json:"total_quantity"`
	InventoryValue float64 `json:"inventory_value"`
}

type InvoiceListFilter struct {
	InvoiceType string
	From        *time.Time
	To          *time.Time
	Limit       int
	Offset      int
}

type CreateInvoiceInput struct {
	InvoiceType   string
	InvoiceName   *string
	AdminUsername *string
	Lines         []domain.InvoiceLine
}

type Repository struct {
	pool *pgxpool.Pool
}

func New(pool *pgxpool.Pool) *Repository {
	return &Repository{pool: pool}
}

func (r *Repository) ListProducts(ctx context.Context, filter ProductListFilter) ([]domain.Product, error) {
	limit := normalizeLimit(filter.Limit)
	offset := normalizeOffset(filter.Offset)
	search := strings.TrimSpace(filter.Search)

	base := `
		SELECT
			id,
			product_name,
			quantity,
			avg_buy_price::double precision,
			last_buy_price::double precision,
			alarm,
			source,
			created_at,
			updated_at
		FROM products
		WHERE ($1 = '' OR product_name ILIKE '%' || $1 || '%')
	`
	args := []any{search}
	argIndex := 2
	if filter.Threshold != nil {
		base += fmt.Sprintf(" AND quantity <= COALESCE(alarm, $%d)", argIndex)
		args = append(args, *filter.Threshold)
		argIndex++
	}
	base += fmt.Sprintf(" ORDER BY id ASC LIMIT $%d OFFSET $%d", argIndex, argIndex+1)
	args = append(args, limit, offset)

	rows, err := r.pool.Query(ctx, base, args...)
	if err != nil {
		return nil, fmt.Errorf("list products: %w", err)
	}
	defer rows.Close()

	products := make([]domain.Product, 0, limit)
	for rows.Next() {
		p, err := scanProduct(rows)
		if err != nil {
			return nil, err
		}
		products = append(products, p)
	}
	if err := rows.Err(); err != nil {
		return nil, fmt.Errorf("iterate products: %w", err)
	}
	return products, nil
}

func (r *Repository) GetProductByID(ctx context.Context, id int64) (*domain.Product, error) {
	row := r.pool.QueryRow(ctx, `
		SELECT
			id,
			product_name,
			quantity,
			avg_buy_price::double precision,
			last_buy_price::double precision,
			alarm,
			source,
			created_at,
			updated_at
		FROM products
		WHERE id = $1
	`, id)
	product, err := scanProductRow(row)
	if err != nil {
		if errors.Is(err, pgx.ErrNoRows) {
			return nil, ErrNotFound
		}
		return nil, fmt.Errorf("get product %d: %w", id, err)
	}
	return &product, nil
}

func (r *Repository) CreateProduct(ctx context.Context, input ProductCreateInput) (domain.Product, error) {
	name := strings.TrimSpace(input.ProductName)
	if name == "" {
		return domain.Product{}, fmt.Errorf("product_name is required")
	}
	if input.Quantity < 0 {
		return domain.Product{}, fmt.Errorf("quantity cannot be negative")
	}
	if input.AvgBuyPrice < 0 || input.LastBuyPrice < 0 {
		return domain.Product{}, fmt.Errorf("prices cannot be negative")
	}

	row := r.pool.QueryRow(ctx, `
		INSERT INTO products (
			product_name,
			quantity,
			avg_buy_price,
			last_buy_price,
			alarm,
			source
		)
		VALUES ($1, $2, $3, $4, $5, $6)
		ON CONFLICT ON CONSTRAINT uq_products_name_normalized
		DO UPDATE SET
			quantity = EXCLUDED.quantity,
			avg_buy_price = EXCLUDED.avg_buy_price,
			last_buy_price = EXCLUDED.last_buy_price,
			alarm = EXCLUDED.alarm,
			source = EXCLUDED.source,
			updated_at = NOW()
		RETURNING
			id,
			product_name,
			quantity,
			avg_buy_price::double precision,
			last_buy_price::double precision,
			alarm,
			source,
			created_at,
			updated_at
	`, name, input.Quantity, input.AvgBuyPrice, input.LastBuyPrice, input.Alarm, input.Source)

	product, err := scanProductRow(row)
	if err != nil {
		return domain.Product{}, fmt.Errorf("create product: %w", err)
	}
	return product, nil
}

func (r *Repository) PatchProduct(ctx context.Context, id int64, input ProductPatchInput) (*domain.Product, error) {
	tx, err := r.pool.Begin(ctx)
	if err != nil {
		return nil, fmt.Errorf("begin patch product tx: %w", err)
	}
	defer tx.Rollback(ctx)

	row := tx.QueryRow(ctx, `
		SELECT
			id,
			product_name,
			quantity,
			avg_buy_price::double precision,
			last_buy_price::double precision,
			alarm,
			source,
			created_at,
			updated_at
		FROM products
		WHERE id = $1
		FOR UPDATE
	`, id)
	product, err := scanProductRow(row)
	if err != nil {
		if errors.Is(err, pgx.ErrNoRows) {
			return nil, ErrNotFound
		}
		return nil, fmt.Errorf("load product for patch: %w", err)
	}

	if input.ProductName != nil {
		name := strings.TrimSpace(*input.ProductName)
		if name == "" {
			return nil, fmt.Errorf("product_name cannot be empty")
		}
		product.ProductName = name
	}
	if input.Quantity != nil {
		if *input.Quantity < 0 {
			return nil, fmt.Errorf("quantity cannot be negative")
		}
		product.Quantity = *input.Quantity
	}
	if input.AvgBuyPrice != nil {
		if *input.AvgBuyPrice < 0 {
			return nil, fmt.Errorf("avg_buy_price cannot be negative")
		}
		product.AvgBuyPrice = *input.AvgBuyPrice
	}
	if input.LastBuyPrice != nil {
		if *input.LastBuyPrice < 0 {
			return nil, fmt.Errorf("last_buy_price cannot be negative")
		}
		product.LastBuyPrice = *input.LastBuyPrice
	}
	if input.Alarm != nil {
		product.Alarm = input.Alarm
	}
	if input.Source != nil {
		product.Source = input.Source
	}

	row = tx.QueryRow(ctx, `
		UPDATE products
		SET
			product_name = $2,
			quantity = $3,
			avg_buy_price = $4,
			last_buy_price = $5,
			alarm = $6,
			source = $7,
			updated_at = NOW()
		WHERE id = $1
		RETURNING
			id,
			product_name,
			quantity,
			avg_buy_price::double precision,
			last_buy_price::double precision,
			alarm,
			source,
			created_at,
			updated_at
	`,
		id,
		product.ProductName,
		product.Quantity,
		product.AvgBuyPrice,
		product.LastBuyPrice,
		product.Alarm,
		product.Source,
	)
	updated, err := scanProductRow(row)
	if err != nil {
		return nil, fmt.Errorf("update product: %w", err)
	}

	if err := tx.Commit(ctx); err != nil {
		return nil, fmt.Errorf("commit patch product tx: %w", err)
	}
	return &updated, nil
}

func (r *Repository) DeleteProduct(ctx context.Context, id int64) error {
	cmd, err := r.pool.Exec(ctx, "DELETE FROM products WHERE id = $1", id)
	if err != nil {
		return fmt.Errorf("delete product %d: %w", id, err)
	}
	if cmd.RowsAffected() == 0 {
		return ErrNotFound
	}
	return nil
}

func (r *Repository) UpsertInventoryRows(ctx context.Context, rows []domain.InventoryImportRow) (int, int, error) {
	if len(rows) == 0 {
		return 0, 0, nil
	}
	tx, err := r.pool.Begin(ctx)
	if err != nil {
		return 0, 0, fmt.Errorf("begin import tx: %w", err)
	}
	defer tx.Rollback(ctx)

	created := 0
	updated := 0
	for _, line := range rows {
		name := strings.TrimSpace(line.ProductName)
		if name == "" {
			continue
		}

		var existingID int64
		err := tx.QueryRow(ctx, "SELECT id FROM products WHERE LOWER(product_name) = LOWER($1)", name).Scan(&existingID)
		if err != nil && !errors.Is(err, pgx.ErrNoRows) {
			return 0, 0, fmt.Errorf("query existing product %q: %w", name, err)
		}

		if errors.Is(err, pgx.ErrNoRows) {
			if _, err := tx.Exec(ctx, `
				INSERT INTO products (
					product_name,
					quantity,
					avg_buy_price,
					last_buy_price,
					alarm,
					source
				) VALUES ($1, $2, $3, $4, $5, $6)
			`,
				name,
				line.Quantity,
				line.AvgBuyPrice,
				line.LastBuyPrice,
				line.Alarm,
				line.Source,
			); err != nil {
				return 0, 0, fmt.Errorf("insert imported product %q: %w", name, err)
			}
			created++
			continue
		}

		if _, err := tx.Exec(ctx, `
			UPDATE products
			SET
				product_name = $2,
				quantity = $3,
				avg_buy_price = $4,
				last_buy_price = $5,
				alarm = $6,
				source = $7,
				updated_at = NOW()
			WHERE id = $1
		`,
			existingID,
			name,
			line.Quantity,
			line.AvgBuyPrice,
			line.LastBuyPrice,
			line.Alarm,
			line.Source,
		); err != nil {
			return 0, 0, fmt.Errorf("update imported product %q: %w", name, err)
		}
		updated++
	}

	if err := tx.Commit(ctx); err != nil {
		return 0, 0, fmt.Errorf("commit import tx: %w", err)
	}
	return created, updated, nil
}

func (r *Repository) GetInventorySummary(ctx context.Context) (InventorySummary, error) {
	row := r.pool.QueryRow(ctx, `
		SELECT
			COUNT(*)::int,
			COALESCE(SUM(quantity), 0)::int,
			COALESCE(SUM(quantity * avg_buy_price), 0)::double precision
		FROM products
	`)
	var summary InventorySummary
	if err := row.Scan(&summary.TotalProducts, &summary.TotalQuantity, &summary.InventoryValue); err != nil {
		return InventorySummary{}, fmt.Errorf("inventory summary: %w", err)
	}
	return summary, nil
}

func (r *Repository) CreatePurchaseInvoice(
	ctx context.Context,
	invoiceName *string,
	adminUsername *string,
	lines []domain.PurchaseLineInput,
) (int64, error) {
	if len(lines) == 0 {
		return 0, fmt.Errorf("lines cannot be empty")
	}

	tx, err := r.pool.Begin(ctx)
	if err != nil {
		return 0, fmt.Errorf("begin purchase tx: %w", err)
	}
	defer tx.Rollback(ctx)

	invoiceLines := make([]domain.InvoiceLine, 0, len(lines))
	totalQty := 0
	totalAmount := 0.0

	for _, line := range lines {
		name := strings.TrimSpace(line.ProductName)
		if name == "" {
			return 0, fmt.Errorf("product_name is required")
		}
		if line.Quantity <= 0 {
			return 0, fmt.Errorf("invalid quantity for %q", name)
		}
		if line.Price <= 0 {
			return 0, fmt.Errorf("invalid price for %q", name)
		}

		var (
			productID  int64
			currentQty int
			currentAvg float64
		)
		err := tx.QueryRow(ctx, `
			SELECT id, quantity, avg_buy_price::double precision
			FROM products
			WHERE LOWER(product_name) = LOWER($1)
			FOR UPDATE
		`, name).Scan(&productID, &currentQty, &currentAvg)
		if err != nil && !errors.Is(err, pgx.ErrNoRows) {
			return 0, fmt.Errorf("load product %q for purchase: %w", name, err)
		}

		if errors.Is(err, pgx.ErrNoRows) {
			if err := tx.QueryRow(ctx, `
				INSERT INTO products (
					product_name,
					quantity,
					avg_buy_price,
					last_buy_price
				) VALUES ($1, $2, $3, $4)
				RETURNING id
			`, name, line.Quantity, line.Price, line.Price).Scan(&productID); err != nil {
				return 0, fmt.Errorf("insert product %q during purchase: %w", name, err)
			}
		} else {
			avgBaseQty := currentQty
			if avgBaseQty < 0 {
				avgBaseQty = 0
			}
			avgBasePrice := currentAvg
			if avgBasePrice <= 0 {
				avgBasePrice = line.Price
			}
			denominator := avgBaseQty + line.Quantity
			newAvg := 0.0
			if denominator > 0 {
				newAvg = ((avgBasePrice * float64(avgBaseQty)) + (line.Price * float64(line.Quantity))) / float64(denominator)
			}
			newQty := currentQty + line.Quantity
			if _, err := tx.Exec(ctx, `
				UPDATE products
				SET
					quantity = $2,
					avg_buy_price = $3,
					last_buy_price = $4,
					updated_at = NOW()
				WHERE id = $1
			`, productID, newQty, newAvg, line.Price); err != nil {
				return 0, fmt.Errorf("update product %q during purchase: %w", name, err)
			}
		}

		lineTotal := line.Price * float64(line.Quantity)
		invoiceLines = append(invoiceLines, domain.InvoiceLine{
			ProductName: name,
			Price:       line.Price,
			Quantity:    line.Quantity,
			LineTotal:   lineTotal,
			CostPrice:   line.Price,
		})
		totalQty += line.Quantity
		totalAmount += lineTotal
	}

	invoiceID, err := insertInvoiceTx(ctx, tx, CreateInvoiceInput{
		InvoiceType:   "purchase",
		InvoiceName:   invoiceName,
		AdminUsername: adminUsername,
		Lines:         invoiceLines,
	})
	if err != nil {
		return 0, err
	}

	if err := tx.Commit(ctx); err != nil {
		return 0, fmt.Errorf("commit purchase tx: %w", err)
	}

	_ = totalQty
	_ = totalAmount
	return invoiceID, nil
}

func (r *Repository) CreateSalesInvoice(
	ctx context.Context,
	invoiceName *string,
	adminUsername *string,
	invoiceType string,
	lines []domain.SalesLineInput,
) (int64, error) {
	if len(lines) == 0 {
		return 0, fmt.Errorf("lines cannot be empty")
	}
	invoiceType = strings.TrimSpace(invoiceType)
	if invoiceType == "" {
		invoiceType = "sales"
	}

	tx, err := r.pool.Begin(ctx)
	if err != nil {
		return 0, fmt.Errorf("begin sales tx: %w", err)
	}
	defer tx.Rollback(ctx)

	invoiceLines := make([]domain.InvoiceLine, 0, len(lines))
	for _, line := range lines {
		name := strings.TrimSpace(line.ProductName)
		if name == "" {
			return 0, fmt.Errorf("product_name is required")
		}
		if line.Quantity <= 0 {
			return 0, fmt.Errorf("invalid quantity for %q", name)
		}

		var (
			productID  int64
			currentQty int
			avgCost    float64
		)
		err := tx.QueryRow(ctx, `
			SELECT id, quantity, avg_buy_price::double precision
			FROM products
			WHERE LOWER(product_name) = LOWER($1)
			FOR UPDATE
		`, name).Scan(&productID, &currentQty, &avgCost)
		if errors.Is(err, pgx.ErrNoRows) {
			return 0, fmt.Errorf("product not found: %s", name)
		}
		if err != nil {
			return 0, fmt.Errorf("load product %q for sales: %w", name, err)
		}

		newQty := currentQty - line.Quantity
		if _, err := tx.Exec(ctx, `
			UPDATE products
			SET quantity = $2, updated_at = NOW()
			WHERE id = $1
		`, productID, newQty); err != nil {
			return 0, fmt.Errorf("update product %q during sales: %w", name, err)
		}

		sellPrice := line.Price
		if sellPrice <= 0 {
			sellPrice = avgCost
		}
		lineTotal := sellPrice * float64(line.Quantity)
		invoiceLines = append(invoiceLines, domain.InvoiceLine{
			ProductName: name,
			Price:       sellPrice,
			Quantity:    line.Quantity,
			LineTotal:   lineTotal,
			CostPrice:   avgCost,
		})
	}

	invoiceID, err := insertInvoiceTx(ctx, tx, CreateInvoiceInput{
		InvoiceType:   invoiceType,
		InvoiceName:   invoiceName,
		AdminUsername: adminUsername,
		Lines:         invoiceLines,
	})
	if err != nil {
		return 0, err
	}

	if err := tx.Commit(ctx); err != nil {
		return 0, fmt.Errorf("commit sales tx: %w", err)
	}
	return invoiceID, nil
}

func insertInvoiceTx(ctx context.Context, tx pgx.Tx, input CreateInvoiceInput) (int64, error) {
	totalQty := 0
	totalAmount := 0.0
	for _, line := range input.Lines {
		totalQty += line.Quantity
		totalAmount += line.LineTotal
	}

	var invoiceID int64
	if err := tx.QueryRow(ctx, `
		INSERT INTO invoices (
			invoice_type,
			total_lines,
			total_qty,
			total_amount,
			invoice_name,
			admin_username
		)
		VALUES ($1, $2, $3, $4, $5, $6)
		RETURNING id
	`, input.InvoiceType, len(input.Lines), totalQty, totalAmount, input.InvoiceName, input.AdminUsername).Scan(&invoiceID); err != nil {
		return 0, fmt.Errorf("insert invoice: %w", err)
	}

	for _, line := range input.Lines {
		if _, err := tx.Exec(ctx, `
			INSERT INTO invoice_lines (
				invoice_id,
				product_name,
				price,
				quantity,
				line_total,
				cost_price
			) VALUES ($1, $2, $3, $4, $5, $6)
		`, invoiceID, line.ProductName, line.Price, line.Quantity, line.LineTotal, line.CostPrice); err != nil {
			return 0, fmt.Errorf("insert invoice line: %w", err)
		}
	}

	return invoiceID, nil
}

func (r *Repository) ListInvoices(ctx context.Context, filter InvoiceListFilter) ([]domain.Invoice, error) {
	limit := normalizeLimit(filter.Limit)
	offset := normalizeOffset(filter.Offset)

	query := `
		SELECT
			id,
			invoice_type,
			created_at,
			total_lines,
			total_qty,
			total_amount::double precision,
			invoice_name,
			admin_username
		FROM invoices
		WHERE ($1 = '' OR invoice_type = $1)
	`
	args := []any{strings.TrimSpace(filter.InvoiceType)}
	idx := 2

	if filter.From != nil {
		query += fmt.Sprintf(" AND created_at >= $%d", idx)
		args = append(args, *filter.From)
		idx++
	}
	if filter.To != nil {
		query += fmt.Sprintf(" AND created_at <= $%d", idx)
		args = append(args, *filter.To)
		idx++
	}
	query += fmt.Sprintf(" ORDER BY id DESC LIMIT $%d OFFSET $%d", idx, idx+1)
	args = append(args, limit, offset)

	rows, err := r.pool.Query(ctx, query, args...)
	if err != nil {
		return nil, fmt.Errorf("list invoices: %w", err)
	}
	defer rows.Close()

	result := make([]domain.Invoice, 0, limit)
	for rows.Next() {
		inv, err := scanInvoice(rows)
		if err != nil {
			return nil, err
		}
		result = append(result, inv)
	}
	if err := rows.Err(); err != nil {
		return nil, fmt.Errorf("iterate invoices: %w", err)
	}
	return result, nil
}

func (r *Repository) GetInvoice(ctx context.Context, id int64) (*domain.Invoice, error) {
	row := r.pool.QueryRow(ctx, `
		SELECT
			id,
			invoice_type,
			created_at,
			total_lines,
			total_qty,
			total_amount::double precision,
			invoice_name,
			admin_username
		FROM invoices
		WHERE id = $1
	`, id)
	invoice, err := scanInvoiceRow(row)
	if err != nil {
		if errors.Is(err, pgx.ErrNoRows) {
			return nil, ErrNotFound
		}
		return nil, fmt.Errorf("get invoice %d: %w", id, err)
	}
	return &invoice, nil
}

func (r *Repository) GetInvoiceLines(ctx context.Context, invoiceID int64) ([]domain.InvoiceLine, error) {
	rows, err := r.pool.Query(ctx, `
		SELECT
			id,
			invoice_id,
			product_name,
			price::double precision,
			quantity,
			line_total::double precision,
			cost_price::double precision
		FROM invoice_lines
		WHERE invoice_id = $1
		ORDER BY id ASC
	`, invoiceID)
	if err != nil {
		return nil, fmt.Errorf("get invoice lines %d: %w", invoiceID, err)
	}
	defer rows.Close()

	lines := make([]domain.InvoiceLine, 0)
	for rows.Next() {
		line, err := scanInvoiceLine(rows)
		if err != nil {
			return nil, err
		}
		lines = append(lines, line)
	}
	if err := rows.Err(); err != nil {
		return nil, fmt.Errorf("iterate invoice lines: %w", err)
	}
	return lines, nil
}

func (r *Repository) UpdateInvoiceName(ctx context.Context, id int64, invoiceName *string) error {
	cmd, err := r.pool.Exec(ctx, `
		UPDATE invoices
		SET invoice_name = $2
		WHERE id = $1
	`, id, invoiceName)
	if err != nil {
		return fmt.Errorf("update invoice name: %w", err)
	}
	if cmd.RowsAffected() == 0 {
		return ErrNotFound
	}
	return nil
}

func (r *Repository) DeleteInvoice(ctx context.Context, id int64) error {
	cmd, err := r.pool.Exec(ctx, "DELETE FROM invoices WHERE id = $1", id)
	if err != nil {
		return fmt.Errorf("delete invoice: %w", err)
	}
	if cmd.RowsAffected() == 0 {
		return ErrNotFound
	}
	return nil
}

func (r *Repository) GetMonthlySummary(ctx context.Context, limit int) ([]domain.MonthlySummary, error) {
	if limit <= 0 {
		limit = 12
	}
	if limit > 120 {
		limit = 120
	}

	rows, err := r.pool.Query(ctx, `
		WITH invoice_months AS (
			SELECT
				TO_CHAR(DATE_TRUNC('month', created_at), 'YYYY-MM') AS month,
				SUM(CASE WHEN invoice_type = 'purchase' THEN total_amount ELSE 0 END)::double precision AS purchase_total,
				SUM(CASE WHEN invoice_type LIKE 'sales%' THEN total_amount ELSE 0 END)::double precision AS sales_total,
				COUNT(*)::int AS invoice_count
			FROM invoices
			GROUP BY 1
		),
		sales_profit AS (
			SELECT
				TO_CHAR(DATE_TRUNC('month', i.created_at), 'YYYY-MM') AS month,
				SUM(il.line_total - il.cost_price * il.quantity)::double precision AS profit
			FROM invoices i
			JOIN invoice_lines il ON il.invoice_id = i.id
			WHERE i.invoice_type LIKE 'sales%'
			GROUP BY 1
		)
		SELECT
			im.month,
			COALESCE(im.purchase_total, 0)::double precision,
			COALESCE(im.sales_total, 0)::double precision,
			COALESCE(sp.profit, 0)::double precision,
			im.invoice_count
		FROM invoice_months im
		LEFT JOIN sales_profit sp ON sp.month = im.month
		ORDER BY im.month DESC
		LIMIT $1
	`, limit)
	if err != nil {
		return nil, fmt.Errorf("monthly summary query: %w", err)
	}
	defer rows.Close()

	list := make([]domain.MonthlySummary, 0, limit)
	for rows.Next() {
		var row domain.MonthlySummary
		if err := rows.Scan(&row.Month, &row.PurchaseTotal, &row.SalesTotal, &row.Profit, &row.InvoiceCount); err != nil {
			return nil, fmt.Errorf("scan monthly summary: %w", err)
		}
		list = append(list, row)
	}
	if err := rows.Err(); err != nil {
		return nil, fmt.Errorf("iterate monthly summary: %w", err)
	}
	return list, nil
}

func (r *Repository) GetMonthlyQuantitySummary(ctx context.Context, limit int) ([]domain.MonthlyQuantitySummary, error) {
	if limit <= 0 {
		limit = 12
	}
	if limit > 120 {
		limit = 120
	}

	rows, err := r.pool.Query(ctx, `
		SELECT
			TO_CHAR(DATE_TRUNC('month', created_at), 'YYYY-MM') AS month,
			COALESCE(SUM(CASE WHEN invoice_type LIKE 'sales%' THEN total_qty ELSE 0 END), 0)::int AS sales_qty,
			COALESCE(SUM(CASE WHEN invoice_type = 'purchase' THEN total_qty ELSE 0 END), 0)::int AS purchase_qty,
			COUNT(CASE WHEN invoice_type LIKE 'sales%' THEN 1 END)::int AS sales_invoices,
			COUNT(CASE WHEN invoice_type = 'purchase' THEN 1 END)::int AS purchase_invoices
		FROM invoices
		GROUP BY 1
		ORDER BY month DESC
		LIMIT $1
	`, limit)
	if err != nil {
		return nil, fmt.Errorf("monthly quantity summary query: %w", err)
	}
	defer rows.Close()

	list := make([]domain.MonthlyQuantitySummary, 0, limit)
	for rows.Next() {
		var row domain.MonthlyQuantitySummary
		if err := rows.Scan(
			&row.Month,
			&row.SalesQty,
			&row.PurchaseQty,
			&row.SalesInvoices,
			&row.PurchaseInvoices,
		); err != nil {
			return nil, fmt.Errorf("scan monthly quantity summary: %w", err)
		}
		row.NetQty = row.PurchaseQty - row.SalesQty
		list = append(list, row)
	}
	if err := rows.Err(); err != nil {
		return nil, fmt.Errorf("iterate monthly quantity summary: %w", err)
	}
	return list, nil
}

func (r *Repository) GetTopSoldProducts(ctx context.Context, days, limit int) ([]domain.TopSoldProduct, error) {
	if limit <= 0 {
		limit = 10
	}
	if limit > 200 {
		limit = 200
	}

	rows, err := r.pool.Query(ctx, `
		SELECT
			il.product_name,
			COALESCE(SUM(il.quantity), 0)::int AS sold_qty,
			COUNT(DISTINCT i.id)::int AS invoice_count,
			MAX(i.created_at) AS last_sold_at
		FROM invoices i
		JOIN invoice_lines il ON il.invoice_id = i.id
		WHERE
			i.invoice_type LIKE 'sales%'
			AND ($1::int <= 0 OR i.created_at >= NOW() - ($1 * INTERVAL '1 day'))
		GROUP BY il.product_name
		ORDER BY sold_qty DESC, il.product_name ASC
		LIMIT $2
	`, days, limit)
	if err != nil {
		return nil, fmt.Errorf("top sold products query: %w", err)
	}
	defer rows.Close()

	list := make([]domain.TopSoldProduct, 0, limit)
	for rows.Next() {
		var (
			row      domain.TopSoldProduct
			lastSold sql.NullTime
		)
		if err := rows.Scan(
			&row.ProductName,
			&row.SoldQty,
			&row.InvoiceCount,
			&lastSold,
		); err != nil {
			return nil, fmt.Errorf("scan top sold product: %w", err)
		}
		if lastSold.Valid {
			value := lastSold.Time
			row.LastSoldAt = &value
		}
		list = append(list, row)
	}
	if err := rows.Err(); err != nil {
		return nil, fmt.Errorf("iterate top sold products: %w", err)
	}
	return list, nil
}

func (r *Repository) GetUnsoldProducts(ctx context.Context, days, limit int) ([]domain.UnsoldProduct, error) {
	if days <= 0 {
		days = 30
	}
	if limit <= 0 {
		limit = 200
	}
	if limit > 5000 {
		limit = 5000
	}

	rows, err := r.pool.Query(ctx, `
		WITH sold_recent AS (
			SELECT DISTINCT LOWER(TRIM(il.product_name)) AS product_name_normalized
			FROM invoices i
			JOIN invoice_lines il ON il.invoice_id = i.id
			WHERE
				i.invoice_type LIKE 'sales%'
				AND i.created_at >= NOW() - ($1 * INTERVAL '1 day')
		)
		SELECT
			p.product_name,
			p.quantity,
			p.avg_buy_price::double precision,
			p.source,
			p.updated_at
		FROM products p
		LEFT JOIN sold_recent s
			ON s.product_name_normalized = LOWER(TRIM(p.product_name))
		WHERE s.product_name_normalized IS NULL
		ORDER BY p.quantity DESC, p.product_name ASC
		LIMIT $2
	`, days, limit)
	if err != nil {
		return nil, fmt.Errorf("unsold products query: %w", err)
	}
	defer rows.Close()

	list := make([]domain.UnsoldProduct, 0, limit)
	for rows.Next() {
		var (
			row    domain.UnsoldProduct
			source sql.NullString
		)
		if err := rows.Scan(
			&row.ProductName,
			&row.Quantity,
			&row.AvgBuyPrice,
			&source,
			&row.UpdatedAt,
		); err != nil {
			return nil, fmt.Errorf("scan unsold product: %w", err)
		}
		if source.Valid {
			value := source.String
			row.Source = &value
		}
		list = append(list, row)
	}
	if err := rows.Err(); err != nil {
		return nil, fmt.Errorf("iterate unsold products: %w", err)
	}
	return list, nil
}

func scanProduct(rows pgx.CollectableRow) (domain.Product, error) {
	return scanProductRow(rows)
}

func scanProductRow(row pgx.Row) (domain.Product, error) {
	var (
		product domain.Product
		alarm   sql.NullInt32
		source  sql.NullString
	)
	if err := row.Scan(
		&product.ID,
		&product.ProductName,
		&product.Quantity,
		&product.AvgBuyPrice,
		&product.LastBuyPrice,
		&alarm,
		&source,
		&product.CreatedAt,
		&product.UpdatedAt,
	); err != nil {
		return domain.Product{}, err
	}
	if alarm.Valid {
		value := int(alarm.Int32)
		product.Alarm = &value
	}
	if source.Valid {
		value := source.String
		product.Source = &value
	}
	return product, nil
}

func scanInvoice(rows pgx.CollectableRow) (domain.Invoice, error) {
	return scanInvoiceRow(rows)
}

func scanInvoiceRow(row pgx.Row) (domain.Invoice, error) {
	var (
		inv   domain.Invoice
		name  sql.NullString
		admin sql.NullString
	)
	if err := row.Scan(
		&inv.ID,
		&inv.InvoiceType,
		&inv.CreatedAt,
		&inv.TotalLines,
		&inv.TotalQty,
		&inv.TotalAmount,
		&name,
		&admin,
	); err != nil {
		return domain.Invoice{}, err
	}
	if name.Valid {
		value := name.String
		inv.InvoiceName = &value
	}
	if admin.Valid {
		value := admin.String
		inv.AdminUsername = &value
	}
	return inv, nil
}

func scanInvoiceLine(row pgx.Row) (domain.InvoiceLine, error) {
	var line domain.InvoiceLine
	if err := row.Scan(
		&line.ID,
		&line.InvoiceID,
		&line.ProductName,
		&line.Price,
		&line.Quantity,
		&line.LineTotal,
		&line.CostPrice,
	); err != nil {
		return domain.InvoiceLine{}, fmt.Errorf("scan invoice line: %w", err)
	}
	return line, nil
}

func normalizeLimit(limit int) int {
	if limit <= 0 {
		return 200
	}
	if limit > 1000 {
		return 1000
	}
	return limit
}

func normalizeOffset(offset int) int {
	if offset < 0 {
		return 0
	}
	return offset
}
