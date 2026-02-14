package repository

import (
	"context"
	"database/sql"
	"encoding/json"
	"errors"
	"fmt"
	"sort"
	"strings"
	"time"

	"backend/internal/domain"

	"github.com/jackc/pgx/v5"
)

type aggregateLine struct {
	Name      string
	Qty       int
	Cost      float64
	LastPrice float64
}

func normalizeName(value string) string {
	return strings.ToLower(strings.TrimSpace(value))
}

func aggregateInvoiceLines(lines []domain.InvoiceLine, useCost bool) map[string]*aggregateLine {
	result := make(map[string]*aggregateLine)
	for _, line := range lines {
		name := strings.TrimSpace(line.ProductName)
		if name == "" {
			continue
		}
		key := normalizeName(name)
		entry, ok := result[key]
		if !ok {
			entry = &aggregateLine{Name: name}
			result[key] = entry
		}
		entry.Name = name
		entry.Qty += line.Quantity
		if useCost {
			entry.Cost += line.Price * float64(line.Quantity)
			entry.LastPrice = line.Price
		}
	}
	return result
}

func collectKeys(a, b map[string]*aggregateLine) []string {
	set := make(map[string]struct{}, len(a)+len(b))
	for key := range a {
		set[key] = struct{}{}
	}
	for key := range b {
		set[key] = struct{}{}
	}
	keys := make([]string, 0, len(set))
	for key := range set {
		keys = append(keys, key)
	}
	sort.Strings(keys)
	return keys
}

func loadInvoiceLinesTx(ctx context.Context, tx pgx.Tx, invoiceID int64) ([]domain.InvoiceLine, error) {
	rows, err := tx.Query(ctx, `
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
		return nil, fmt.Errorf("query invoice lines %d: %w", invoiceID, err)
	}
	defer rows.Close()

	items := make([]domain.InvoiceLine, 0)
	for rows.Next() {
		line, scanErr := scanInvoiceLine(rows)
		if scanErr != nil {
			return nil, scanErr
		}
		items = append(items, line)
	}
	if err := rows.Err(); err != nil {
		return nil, fmt.Errorf("iterate invoice lines %d: %w", invoiceID, err)
	}
	return items, nil
}

func loadProductForUpdate(ctx context.Context, tx pgx.Tx, name string) (int64, int, float64, float64, error) {
	var (
		id       int64
		quantity int
		avgBuy   float64
		lastBuy  float64
	)
	err := tx.QueryRow(ctx, `
		SELECT
			id,
			quantity,
			avg_buy_price::double precision,
			last_buy_price::double precision
		FROM products
		WHERE LOWER(product_name) = LOWER($1)
		FOR UPDATE
	`, name).Scan(&id, &quantity, &avgBuy, &lastBuy)
	if errors.Is(err, pgx.ErrNoRows) {
		return 0, 0, 0, 0, ErrNotFound
	}
	if err != nil {
		return 0, 0, 0, 0, fmt.Errorf("load product %q: %w", name, err)
	}
	return id, quantity, avgBuy, lastBuy, nil
}

func validateNewInvoiceLines(lines []domain.InvoiceLine) ([]domain.InvoiceLine, error) {
	cleaned := make([]domain.InvoiceLine, 0, len(lines))
	for _, line := range lines {
		name := strings.TrimSpace(line.ProductName)
		if name == "" {
			return nil, fmt.Errorf("product_name is required")
		}
		if line.Quantity <= 0 {
			return nil, fmt.Errorf("invalid quantity for %q", name)
		}
		if line.Price <= 0 {
			return nil, fmt.Errorf("invalid price for %q", name)
		}
		cleaned = append(cleaned, domain.InvoiceLine{
			ProductName: name,
			Price:       line.Price,
			Quantity:    line.Quantity,
			LineTotal:   line.Price * float64(line.Quantity),
			CostPrice:   line.CostPrice,
		})
	}
	return cleaned, nil
}

func applySalesChangeTx(ctx context.Context, tx pgx.Tx, oldLines, newLines []domain.InvoiceLine) error {
	oldMap := aggregateInvoiceLines(oldLines, false)
	newMap := aggregateInvoiceLines(newLines, false)
	keys := collectKeys(oldMap, newMap)

	for _, key := range keys {
		oldQty := 0
		newQty := 0
		name := ""
		if oldEntry := oldMap[key]; oldEntry != nil {
			oldQty = oldEntry.Qty
			name = oldEntry.Name
		}
		if newEntry := newMap[key]; newEntry != nil {
			newQty = newEntry.Qty
			name = newEntry.Name
		}

		delta := oldQty - newQty
		if delta == 0 {
			continue
		}

		productID, currentQty, _, _, err := loadProductForUpdate(ctx, tx, name)
		if errors.Is(err, ErrNotFound) {
			return fmt.Errorf("product not found in inventory: %s", name)
		}
		if err != nil {
			return err
		}

		updatedQty := currentQty + delta
		if _, err := tx.Exec(ctx, `
			UPDATE products
			SET quantity = $2, updated_at = NOW()
			WHERE id = $1
		`, productID, updatedQty); err != nil {
			return fmt.Errorf("update sales product %s: %w", name, err)
		}
	}
	return nil
}

func applyPurchaseChangeTx(ctx context.Context, tx pgx.Tx, oldLines, newLines []domain.InvoiceLine) error {
	oldMap := aggregateInvoiceLines(oldLines, true)
	newMap := aggregateInvoiceLines(newLines, true)
	keys := collectKeys(oldMap, newMap)

	for _, key := range keys {
		oldQty := 0
		oldCost := 0.0
		newQty := 0
		newCost := 0.0
		newLastPrice := 0.0
		name := ""

		if oldEntry := oldMap[key]; oldEntry != nil {
			oldQty = oldEntry.Qty
			oldCost = oldEntry.Cost
			name = oldEntry.Name
		}
		if newEntry := newMap[key]; newEntry != nil {
			newQty = newEntry.Qty
			newCost = newEntry.Cost
			newLastPrice = newEntry.LastPrice
			name = newEntry.Name
		}

		productID, currentQty, currentAvg, currentLast, err := loadProductForUpdate(ctx, tx, name)
		if errors.Is(err, ErrNotFound) {
			return fmt.Errorf("product not found in inventory: %s", name)
		}
		if err != nil {
			return err
		}

		remainingQty := currentQty - oldQty
		remainingCost := (currentAvg * float64(currentQty)) - oldCost
		avgBaseQty := remainingQty
		if avgBaseQty < 0 {
			avgBaseQty = 0
		}
		avgBaseCost := remainingCost
		if remainingQty <= 0 {
			avgBaseCost = 0
		}
		avgDenominator := avgBaseQty + newQty
		newAvg := 0.0
		if avgDenominator > 0 {
			newAvg = (avgBaseCost + newCost) / float64(avgDenominator)
		}
		updatedQty := remainingQty + newQty
		updatedLast := currentLast
		if newQty > 0 && newLastPrice > 0 {
			updatedLast = newLastPrice
		}

		if _, err := tx.Exec(ctx, `
			UPDATE products
			SET
				quantity = $2,
				avg_buy_price = $3,
				last_buy_price = $4,
				updated_at = NOW()
			WHERE id = $1
		`, productID, updatedQty, newAvg, updatedLast); err != nil {
			return fmt.Errorf("update purchase product %s: %w", name, err)
		}
	}
	return nil
}

func upsertInvoiceLinesTx(ctx context.Context, tx pgx.Tx, invoiceID int64, invoiceType string, lines []domain.InvoiceLine) error {
	if _, err := tx.Exec(ctx, "DELETE FROM invoice_lines WHERE invoice_id = $1", invoiceID); err != nil {
		return fmt.Errorf("clear invoice lines: %w", err)
	}
	for _, line := range lines {
		costPrice := line.CostPrice
		if invoiceType == "purchase" {
			costPrice = line.Price
		}
		if _, err := tx.Exec(ctx, `
			INSERT INTO invoice_lines (
				invoice_id,
				product_name,
				price,
				quantity,
				line_total,
				cost_price
			) VALUES ($1, $2, $3, $4, $5, $6)
		`, invoiceID, line.ProductName, line.Price, line.Quantity, line.LineTotal, costPrice); err != nil {
			return fmt.Errorf("insert invoice line for invoice %d: %w", invoiceID, err)
		}
	}
	return nil
}

func updateInvoiceTotalsTx(ctx context.Context, tx pgx.Tx, invoiceID int64, invoiceName *string, lines []domain.InvoiceLine) error {
	totalQty := 0
	totalAmount := 0.0
	for _, line := range lines {
		totalQty += line.Quantity
		totalAmount += line.LineTotal
	}
	if _, err := tx.Exec(ctx, `
		UPDATE invoices
		SET
			total_lines = $2,
			total_qty = $3,
			total_amount = $4,
			invoice_name = $5
		WHERE id = $1
	`, invoiceID, len(lines), totalQty, totalAmount, invoiceName); err != nil {
		return fmt.Errorf("update invoice totals: %w", err)
	}
	return nil
}

func (r *Repository) UpdateInvoiceLinesReconciled(
	ctx context.Context,
	invoiceID int64,
	invoiceName *string,
	newLines []domain.InvoiceLine,
) error {
	cleanedLines, err := validateNewInvoiceLines(newLines)
	if err != nil {
		return err
	}

	tx, err := r.pool.Begin(ctx)
	if err != nil {
		return fmt.Errorf("begin update invoice tx: %w", err)
	}
	defer tx.Rollback(ctx)

	var invoiceType string
	err = tx.QueryRow(ctx, `
		SELECT invoice_type
		FROM invoices
		WHERE id = $1
		FOR UPDATE
	`, invoiceID).Scan(&invoiceType)
	if errors.Is(err, pgx.ErrNoRows) {
		return ErrNotFound
	}
	if err != nil {
		return fmt.Errorf("load invoice %d: %w", invoiceID, err)
	}

	oldLines, err := loadInvoiceLinesTx(ctx, tx, invoiceID)
	if err != nil {
		return err
	}

	if strings.HasPrefix(invoiceType, "sales") {
		if err := applySalesChangeTx(ctx, tx, oldLines, cleanedLines); err != nil {
			return err
		}
	} else if invoiceType == "purchase" {
		if err := applyPurchaseChangeTx(ctx, tx, oldLines, cleanedLines); err != nil {
			return err
		}
	} else {
		return fmt.Errorf("unsupported invoice type: %s", invoiceType)
	}

	if err := upsertInvoiceLinesTx(ctx, tx, invoiceID, invoiceType, cleanedLines); err != nil {
		return err
	}
	if err := updateInvoiceTotalsTx(ctx, tx, invoiceID, invoiceName, cleanedLines); err != nil {
		return err
	}

	if err := tx.Commit(ctx); err != nil {
		return fmt.Errorf("commit update invoice tx: %w", err)
	}
	return nil
}

func (r *Repository) DeleteInvoiceReconciled(ctx context.Context, invoiceID int64) error {
	tx, err := r.pool.Begin(ctx)
	if err != nil {
		return fmt.Errorf("begin delete invoice tx: %w", err)
	}
	defer tx.Rollback(ctx)

	var invoiceType string
	err = tx.QueryRow(ctx, `
		SELECT invoice_type
		FROM invoices
		WHERE id = $1
		FOR UPDATE
	`, invoiceID).Scan(&invoiceType)
	if errors.Is(err, pgx.ErrNoRows) {
		return ErrNotFound
	}
	if err != nil {
		return fmt.Errorf("load invoice %d: %w", invoiceID, err)
	}

	oldLines, err := loadInvoiceLinesTx(ctx, tx, invoiceID)
	if err != nil {
		return err
	}

	if strings.HasPrefix(invoiceType, "sales") {
		if err := applySalesChangeTx(ctx, tx, oldLines, nil); err != nil {
			return err
		}
	} else if invoiceType == "purchase" {
		if err := applyPurchaseChangeTx(ctx, tx, oldLines, nil); err != nil {
			return err
		}
	} else {
		return fmt.Errorf("unsupported invoice type: %s", invoiceType)
	}

	if _, err := tx.Exec(ctx, "DELETE FROM invoices WHERE id = $1", invoiceID); err != nil {
		return fmt.Errorf("delete invoice %d: %w", invoiceID, err)
	}
	if err := tx.Commit(ctx); err != nil {
		return fmt.Errorf("commit delete invoice tx: %w", err)
	}
	return nil
}

func (r *Repository) GetInvoiceStats(
	ctx context.Context,
	invoiceType string,
) (int, float64, error) {
	var (
		count int
		total float64
	)
	invoiceType = strings.TrimSpace(invoiceType)
	if err := r.pool.QueryRow(ctx, `
		SELECT
			COUNT(*)::int,
			COALESCE(SUM(total_amount), 0)::double precision
		FROM invoices
		WHERE (
			$1 = ''
			OR ($1 = 'sales' AND invoice_type LIKE 'sales%')
			OR invoice_type = $1
		)
	`, invoiceType).Scan(&count, &total); err != nil {
		return 0, 0, fmt.Errorf("get invoice stats: %w", err)
	}
	return count, total, nil
}

func (r *Repository) ListInvoicesBetween(
	ctx context.Context,
	start time.Time,
	end time.Time,
	productFilter string,
	fuzzy bool,
	idFrom *int64,
	idTo *int64,
) ([]domain.Invoice, error) {
	conditions := []string{"i.created_at >= $1", "i.created_at <= $2"}
	params := []any{start, end}
	index := 3

	if idFrom != nil {
		conditions = append(conditions, fmt.Sprintf("i.id >= $%d", index))
		params = append(params, *idFrom)
		index++
	}
	if idTo != nil {
		conditions = append(conditions, fmt.Sprintf("i.id <= $%d", index))
		params = append(params, *idTo)
		index++
	}

	whereClause := strings.Join(conditions, " AND ")
	query := ""
	filterValue := strings.TrimSpace(productFilter)
	if filterValue != "" {
		op := "="
		if fuzzy {
			op = "ILIKE"
			filterValue = "%" + filterValue + "%"
		}
		params = append(params, filterValue)
		query = fmt.Sprintf(`
			WITH ranked_lines AS (
				SELECT
					i.id,
					i.invoice_type,
					i.created_at,
					i.total_lines,
					i.total_qty,
					i.total_amount::double precision,
					i.invoice_name,
					i.admin_username,
					il.product_name,
					il.price::double precision,
					il.quantity,
					il.line_total::double precision,
					il.cost_price::double precision,
					ROW_NUMBER() OVER (
						PARTITION BY i.id
						ORDER BY il.id
					)::int AS row_number
				FROM invoices i
				JOIN invoice_lines il ON il.invoice_id = i.id
				WHERE %s
			)
			SELECT
				id,
				invoice_type,
				created_at,
				total_lines,
				total_qty,
				total_amount::double precision,
				invoice_name,
				admin_username,
				COALESCE(
					JSON_AGG(
						JSON_BUILD_OBJECT(
							'row_number', row_number,
							'product_name', product_name,
							'price', price,
							'quantity', quantity,
							'line_total', line_total,
							'cost_price', cost_price
						)
						ORDER BY row_number
					),
					'[]'::json
				)
			FROM ranked_lines
			WHERE product_name %s $%d
			GROUP BY
				id,
				invoice_type,
				created_at,
				total_lines,
				total_qty,
				total_amount,
				invoice_name,
				admin_username
			ORDER BY id DESC
		`, whereClause, op, index)
	} else {
		query = fmt.Sprintf(`
			SELECT
				i.id,
				i.invoice_type,
				i.created_at,
				i.total_lines,
				i.total_qty,
				i.total_amount::double precision,
				i.invoice_name,
				i.admin_username,
				'[]'::json
			FROM invoices i
			WHERE %s
			ORDER BY i.id DESC
		`, whereClause)
	}

	rows, err := r.pool.Query(ctx, query, params...)
	if err != nil {
		return nil, fmt.Errorf("list invoices between: %w", err)
	}
	defer rows.Close()

	items := make([]domain.Invoice, 0)
	for rows.Next() {
		var (
			item     domain.Invoice
			name     sql.NullString
			admin    sql.NullString
			rawMatch []byte
		)
		if err := rows.Scan(
			&item.ID,
			&item.InvoiceType,
			&item.CreatedAt,
			&item.TotalLines,
			&item.TotalQty,
			&item.TotalAmount,
			&name,
			&admin,
			&rawMatch,
		); err != nil {
			return nil, fmt.Errorf("scan invoices between row: %w", err)
		}
		if name.Valid {
			value := name.String
			item.InvoiceName = &value
		}
		if admin.Valid {
			value := admin.String
			item.AdminUsername = &value
		}
		if len(rawMatch) > 0 {
			if err := json.Unmarshal(rawMatch, &item.ProductMatches); err != nil {
				return nil, fmt.Errorf(
					"decode invoice product matches for invoice %d: %w",
					item.ID,
					err,
				)
			}
		}
		items = append(items, item)
	}
	if err := rows.Err(); err != nil {
		return nil, fmt.Errorf("iterate invoices between: %w", err)
	}
	return items, nil
}

func (r *Repository) RenameInvoiceProducts(
	ctx context.Context,
	changes [][2]string,
) (domain.ProductRenameResult, error) {
	if len(changes) == 0 {
		return domain.ProductRenameResult{}, nil
	}

	tx, err := r.pool.Begin(ctx)
	if err != nil {
		return domain.ProductRenameResult{}, fmt.Errorf("begin rename tx: %w", err)
	}
	defer tx.Rollback(ctx)

	result := domain.ProductRenameResult{}
	invoiceSet := map[int64]struct{}{}
	for _, pair := range changes {
		oldValue := strings.TrimSpace(pair[0])
		newValue := strings.TrimSpace(pair[1])
		if oldValue == "" || newValue == "" || oldValue == newValue {
			continue
		}

		rows, queryErr := tx.Query(ctx, "SELECT invoice_id FROM invoice_lines WHERE product_name = $1", oldValue)
		if queryErr != nil {
			return domain.ProductRenameResult{}, fmt.Errorf("query invoice ids for %q: %w", oldValue, queryErr)
		}
		for rows.Next() {
			var invoiceID int64
			if scanErr := rows.Scan(&invoiceID); scanErr != nil {
				rows.Close()
				return domain.ProductRenameResult{}, fmt.Errorf("scan invoice id for %q: %w", oldValue, scanErr)
			}
			invoiceSet[invoiceID] = struct{}{}
		}
		if err := rows.Err(); err != nil {
			rows.Close()
			return domain.ProductRenameResult{}, fmt.Errorf("iterate invoice ids for %q: %w", oldValue, err)
		}
		rows.Close()

		cmd, execErr := tx.Exec(ctx,
			"UPDATE invoice_lines SET product_name = $2 WHERE product_name = $1",
			oldValue,
			newValue,
		)
		if execErr != nil {
			return domain.ProductRenameResult{}, fmt.Errorf("rename invoice lines %q => %q: %w", oldValue, newValue, execErr)
		}
		result.UpdatedLines += int(cmd.RowsAffected())
	}

	result.UpdatedInvoiceIDs = make([]int64, 0, len(invoiceSet))
	for invoiceID := range invoiceSet {
		result.UpdatedInvoiceIDs = append(result.UpdatedInvoiceIDs, invoiceID)
	}
	sort.Slice(result.UpdatedInvoiceIDs, func(i, j int) bool {
		return result.UpdatedInvoiceIDs[i] < result.UpdatedInvoiceIDs[j]
	})

	if err := tx.Commit(ctx); err != nil {
		return domain.ProductRenameResult{}, fmt.Errorf("commit rename tx: %w", err)
	}
	return result, nil
}

func (r *Repository) SetDefaultAdmin(ctx context.Context) error {
	var exists bool
	if err := r.pool.QueryRow(ctx,
		"SELECT EXISTS(SELECT 1 FROM admins WHERE username = $1)",
		"reza",
	).Scan(&exists); err != nil {
		return fmt.Errorf("check default admin: %w", err)
	}
	if exists {
		return nil
	}
	if _, err := r.pool.Exec(ctx, `
		INSERT INTO admins (username, password, role, auto_lock_minutes)
		VALUES ($1, $2, $3, $4)
	`, "reza", "reza1375", "manager", 1); err != nil {
		return fmt.Errorf("create default admin: %w", err)
	}
	return nil
}

func (r *Repository) AuthenticateAdmin(ctx context.Context, username, password string) (*domain.AdminUser, error) {
	var (
		adminID        int64
		role           string
		autoLock       int
		storedPassword string
	)
	err := r.pool.QueryRow(ctx, `
		SELECT id, role, auto_lock_minutes, password
		FROM admins
		WHERE username = $1
	`, strings.TrimSpace(username)).Scan(&adminID, &role, &autoLock, &storedPassword)
	if errors.Is(err, pgx.ErrNoRows) {
		return nil, nil
	}
	if err != nil {
		return nil, fmt.Errorf("authenticate admin query: %w", err)
	}
	if storedPassword != password {
		return nil, nil
	}
	return &domain.AdminUser{
		AdminID:         adminID,
		Username:        strings.TrimSpace(username),
		Role:            role,
		AutoLockMinutes: autoLock,
	}, nil
}

func (r *Repository) ListAdmins(ctx context.Context) ([]domain.AdminUser, error) {
	rows, err := r.pool.Query(ctx, `
		SELECT id, username, role, auto_lock_minutes
		FROM admins
		ORDER BY username ASC
	`)
	if err != nil {
		return nil, fmt.Errorf("list admins: %w", err)
	}
	defer rows.Close()
	items := make([]domain.AdminUser, 0)
	for rows.Next() {
		var row domain.AdminUser
		if err := rows.Scan(&row.AdminID, &row.Username, &row.Role, &row.AutoLockMinutes); err != nil {
			return nil, fmt.Errorf("scan admin: %w", err)
		}
		items = append(items, row)
	}
	if err := rows.Err(); err != nil {
		return nil, fmt.Errorf("iterate admins: %w", err)
	}
	return items, nil
}

func (r *Repository) CreateAdmin(
	ctx context.Context,
	username, password, role string,
	autoLockMinutes int,
) (*domain.AdminUser, error) {
	username = strings.TrimSpace(username)
	role = strings.ToLower(strings.TrimSpace(role))
	if username == "" {
		return nil, fmt.Errorf("username is required")
	}
	if password == "" {
		return nil, fmt.Errorf("password is required")
	}
	if role != "manager" && role != "employee" {
		return nil, fmt.Errorf("role must be manager or employee")
	}
	if autoLockMinutes <= 0 {
		autoLockMinutes = 1
	}
	if autoLockMinutes > 60 {
		autoLockMinutes = 60
	}

	var created domain.AdminUser
	err := r.pool.QueryRow(ctx, `
		INSERT INTO admins (username, password, role, auto_lock_minutes)
		VALUES ($1, $2, $3, $4)
		RETURNING id, username, role, auto_lock_minutes
	`, username, password, role, autoLockMinutes).Scan(
		&created.AdminID,
		&created.Username,
		&created.Role,
		&created.AutoLockMinutes,
	)
	if err != nil {
		return nil, fmt.Errorf("create admin: %w", err)
	}
	return &created, nil
}

func (r *Repository) UpdateAdminPassword(ctx context.Context, adminID int64, password string) error {
	if strings.TrimSpace(password) == "" {
		return fmt.Errorf("password is required")
	}
	cmd, err := r.pool.Exec(ctx,
		"UPDATE admins SET password = $2 WHERE id = $1",
		adminID,
		password,
	)
	if err != nil {
		return fmt.Errorf("update admin password: %w", err)
	}
	if cmd.RowsAffected() == 0 {
		return ErrNotFound
	}
	return nil
}

func (r *Repository) UpdateAdminAutoLock(ctx context.Context, adminID int64, minutes int) error {
	if minutes < 1 || minutes > 60 {
		return fmt.Errorf("auto_lock_minutes must be between 1 and 60")
	}
	cmd, err := r.pool.Exec(ctx,
		"UPDATE admins SET auto_lock_minutes = $2 WHERE id = $1",
		adminID,
		minutes,
	)
	if err != nil {
		return fmt.Errorf("update admin auto_lock_minutes: %w", err)
	}
	if cmd.RowsAffected() == 0 {
		return ErrNotFound
	}
	return nil
}

func (r *Repository) DeleteAdmin(ctx context.Context, adminID int64) error {
	cmd, err := r.pool.Exec(ctx,
		"DELETE FROM admins WHERE id = $1",
		adminID,
	)
	if err != nil {
		return fmt.Errorf("delete admin: %w", err)
	}
	if cmd.RowsAffected() == 0 {
		return ErrNotFound
	}
	return nil
}

func (r *Repository) GetAdminByID(ctx context.Context, adminID int64) (*domain.AdminUser, error) {
	row := r.pool.QueryRow(ctx, `
		SELECT id, username, role, auto_lock_minutes
		FROM admins
		WHERE id = $1
	`, adminID)
	var admin domain.AdminUser
	if err := row.Scan(&admin.AdminID, &admin.Username, &admin.Role, &admin.AutoLockMinutes); err != nil {
		if errors.Is(err, pgx.ErrNoRows) {
			return nil, ErrNotFound
		}
		return nil, fmt.Errorf("get admin by id: %w", err)
	}
	return &admin, nil
}

func (r *Repository) LogAction(
	ctx context.Context,
	actionType, title, details string,
	adminUsername *string,
) error {
	actionType = strings.TrimSpace(actionType)
	title = strings.TrimSpace(title)
	if actionType == "" || title == "" {
		return fmt.Errorf("action_type and title are required")
	}
	if details == "" {
		details = "-"
	}
	if _, err := r.pool.Exec(ctx, `
		INSERT INTO actions (
			admin_username,
			action_type,
			title,
			details
		) VALUES ($1, $2, $3, $4)
	`, adminUsername, actionType, title, details); err != nil {
		return fmt.Errorf("log action: %w", err)
	}
	return nil
}

func (r *Repository) ListActions(
	ctx context.Context,
	limit, offset int,
	search string,
) ([]domain.ActionEntry, error) {
	limit = normalizeLimit(limit)
	offset = normalizeOffset(offset)
	search = strings.TrimSpace(search)

	rows, err := r.pool.Query(ctx, `
		SELECT
			id,
			created_at,
			admin_username,
			action_type,
			title,
			details
		FROM actions
		WHERE ($1 = '' OR title ILIKE '%' || $1 || '%' OR details ILIKE '%' || $1 || '%' OR COALESCE(admin_username, '') ILIKE '%' || $1 || '%')
		ORDER BY id DESC
		LIMIT $2 OFFSET $3
	`, search, limit, offset)
	if err != nil {
		return nil, fmt.Errorf("list actions: %w", err)
	}
	defer rows.Close()

	items := make([]domain.ActionEntry, 0, limit)
	for rows.Next() {
		var (
			row   domain.ActionEntry
			admin sql.NullString
		)
		if err := rows.Scan(
			&row.ActionID,
			&row.CreatedAt,
			&admin,
			&row.ActionType,
			&row.Title,
			&row.Details,
		); err != nil {
			return nil, fmt.Errorf("scan action: %w", err)
		}
		if admin.Valid {
			value := admin.String
			row.AdminUsername = &value
		}
		items = append(items, row)
	}
	if err := rows.Err(); err != nil {
		return nil, fmt.Errorf("iterate actions: %w", err)
	}
	return items, nil
}

func (r *Repository) CountActions(ctx context.Context, search string) (int, error) {
	search = strings.TrimSpace(search)
	var count int
	if err := r.pool.QueryRow(ctx, `
		SELECT COUNT(*)::int
		FROM actions
		WHERE ($1 = '' OR title ILIKE '%' || $1 || '%' OR details ILIKE '%' || $1 || '%' OR COALESCE(admin_username, '') ILIKE '%' || $1 || '%')
	`, search).Scan(&count); err != nil {
		return 0, fmt.Errorf("count actions: %w", err)
	}
	return count, nil
}

func (r *Repository) PreviewSales(
	ctx context.Context,
	rows []domain.SalesPreviewRow,
) ([]domain.SalesPreviewRow, int, int, error) {
	products, err := r.ListAllProducts(ctx)
	if err != nil {
		return nil, 0, 0, err
	}
	available := map[string]int{}
	costMap := map[string]float64{}
	sellMap := map[string]float64{}
	nameMap := map[string]string{}
	for _, product := range products {
		key := normalizeName(product.ProductName)
		available[key] = product.Quantity
		costMap[key] = product.AvgBuyPrice
		sellMap[key] = product.SellPrice
		if _, exists := nameMap[key]; !exists {
			nameMap[key] = product.ProductName
		}
	}

	result := make([]domain.SalesPreviewRow, 0, len(rows))
	success := 0
	errorsCount := 0
	for _, row := range rows {
		name := strings.TrimSpace(row.ProductName)
		if name == "" {
			result = append(result, domain.SalesPreviewRow{
				ProductName:  "",
				QuantitySold: 0,
				SellPrice:    0,
				CostPrice:    0,
				Status:       "Error",
				Message:      "Missing product name",
			})
			errorsCount++
			continue
		}
		if row.QuantitySold <= 0 {
			result = append(result, domain.SalesPreviewRow{
				ProductName:  name,
				QuantitySold: row.QuantitySold,
				SellPrice:    row.SellPrice,
				CostPrice:    0,
				Status:       "Error",
				Message:      "Invalid quantity",
			})
			errorsCount++
			continue
		}
		key := normalizeName(name)
		availableQty, ok := available[key]
		if !ok {
			result = append(result, domain.SalesPreviewRow{
				ProductName:  name,
				QuantitySold: row.QuantitySold,
				SellPrice:    row.SellPrice,
				CostPrice:    0,
				Status:       "Error",
				Message:      "Product not found",
			})
			errorsCount++
			continue
		}
		costPrice := costMap[key]
		sellPrice := row.SellPrice
		if sellPrice <= 0 {
			if storedSell := sellMap[key]; storedSell > 0 {
				sellPrice = storedSell
			} else {
				sellPrice = costPrice
			}
		}
		available[key] = availableQty - row.QuantitySold
		result = append(result, domain.SalesPreviewRow{
			ProductName:  name,
			QuantitySold: row.QuantitySold,
			SellPrice:    sellPrice,
			CostPrice:    costPrice,
			Status:       "OK",
			Message:      "Will update stock",
			ResolvedName: nameMap[key],
		})
		success++
	}
	return result, success, errorsCount, nil
}
