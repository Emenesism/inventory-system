package main

import (
	"bytes"
	"context"
	"encoding/csv"
	"errors"
	"flag"
	"fmt"
	"log"
	"math"
	"os"
	"os/exec"
	"strconv"
	"strings"
	"time"

	"backend/internal/config"
	"backend/internal/db"
	"backend/internal/domain"
	"backend/internal/excel"

	"github.com/jackc/pgx/v5"
	"github.com/jackc/pgx/v5/pgxpool"
)

type options struct {
	stockPath          string
	sqlitePath         string
	sellPricePath      string
	sellPriceThreshold float64
	replace            bool
	syncProducts       bool
}

type legacyData struct {
	admins       []legacyAdmin
	invoices     []legacyInvoice
	invoiceLines []legacyInvoiceLine
	actions      []legacyAction
	basalamIDs   []legacyBasalamID
}

type legacyAdmin struct {
	Username        string
	PasswordHash    string
	Role            string
	AutoLockMinutes int
	CreatedAt       string
}

type legacyInvoice struct {
	ID            int64
	InvoiceType   string
	CreatedAt     string
	TotalLines    int
	TotalQty      int
	TotalAmount   float64
	InvoiceName   string
	AdminUsername string
}

type legacyInvoiceLine struct {
	ID          int64
	InvoiceID   int64
	ProductName string
	Price       float64
	Quantity    int
	LineTotal   float64
	CostPrice   float64
}

type legacyAction struct {
	ID            int64
	CreatedAt     string
	AdminUsername string
	ActionType    string
	Title         string
	Details       string
}

type legacyBasalamID struct {
	ID      string
	SavedAt string
}

type sellPriceSyncStats struct {
	ExactMatched      int
	FuzzyMatched      int
	Unchanged         int
	PriceRows         int
	DuplicateNameRows int
}

func main() {
	opts := parseFlags()

	cfg, err := config.Load()
	if err != nil {
		log.Fatalf("config error: %v", err)
	}

	ctx := context.Background()
	pool, err := db.NewPool(ctx, cfg.DatabaseURL)
	if err != nil {
		log.Fatalf("database error: %v", err)
	}
	defer pool.Close()

	if err := db.RunMigrations(ctx, pool); err != nil {
		log.Fatalf("migration error: %v", err)
	}

	stockRows, err := readStockRows(opts.stockPath)
	if err != nil {
		log.Fatalf("read stock file: %v", err)
	}
	if opts.sellPricePath != "" {
		priceRows, err := readSellPriceRows(opts.sellPricePath)
		if err != nil {
			log.Fatalf("read sell price file: %v", err)
		}
		stats := applySellPriceOverrides(
			stockRows,
			priceRows,
			opts.sellPriceThreshold,
		)
		log.Printf(
			"sell price sync complete: price_rows=%d exact=%d fuzzy=%d unchanged=%d duplicate_names=%d threshold=%.2f",
			stats.PriceRows,
			stats.ExactMatched,
			stats.FuzzyMatched,
			stats.Unchanged,
			stats.DuplicateNameRows,
			opts.sellPriceThreshold,
		)
	}

	legacy, err := readLegacySQLite(opts.sqlitePath)
	if err != nil {
		log.Fatalf("read sqlite data: %v", err)
	}

	if err := importAll(ctx, pool, stockRows, legacy, opts); err != nil {
		log.Fatalf("import failed: %v", err)
	}

	log.Printf(
		"import complete: stock=%d admins=%d invoices=%d invoice_lines=%d actions=%d basalam_ids=%d",
		len(stockRows),
		len(legacy.admins),
		len(legacy.invoices),
		len(legacy.invoiceLines),
		len(legacy.actions),
		len(legacy.basalamIDs),
	)
}

func parseFlags() options {
	var opts options
	flag.StringVar(
		&opts.stockPath,
		"stock",
		"../stock.xlsx",
		"path to stock.xlsx file",
	)
	flag.StringVar(
		&opts.sqlitePath,
		"sqlite",
		"../invoices.db",
		"path to legacy invoices.db file",
	)
	flag.StringVar(
		&opts.sellPricePath,
		"sell-price",
		"",
		"optional path to price excel (Product Name + Price) for sell_price mapping",
	)
	flag.Float64Var(
		&opts.sellPriceThreshold,
		"sell-price-threshold",
		96,
		"minimum similarity percent (0-100) for fuzzy sell_price mapping",
	)
	flag.BoolVar(
		&opts.replace,
		"replace",
		false,
		"truncate target tables before importing",
	)
	flag.BoolVar(
		&opts.syncProducts,
		"sync-products",
		true,
		"also upsert stock rows into products table",
	)
	flag.Parse()
	if opts.sellPriceThreshold < 0 || opts.sellPriceThreshold > 100 {
		log.Fatalf("invalid --sell-price-threshold: %.2f (expected 0..100)", opts.sellPriceThreshold)
	}
	return opts
}

func readStockRows(path string) ([]domain.InventoryImportRow, error) {
	file, err := os.Open(path)
	if err != nil {
		return nil, fmt.Errorf("open %s: %w", path, err)
	}
	defer file.Close()

	rows, err := excel.ParseInventoryRows(file)
	if err != nil {
		return nil, fmt.Errorf("parse %s: %w", path, err)
	}
	return rows, nil
}

func readSellPriceRows(path string) ([]domain.ProductPriceRow, error) {
	file, err := os.Open(path)
	if err != nil {
		return nil, fmt.Errorf("open %s: %w", path, err)
	}
	defer file.Close()

	rows, _, err := excel.ParseProductPriceRows(path, file)
	if err != nil {
		return nil, fmt.Errorf("parse %s: %w", path, err)
	}
	return rows, nil
}

func applySellPriceOverrides(
	stockRows []domain.InventoryImportRow,
	priceRows []domain.ProductPriceRow,
	threshold float64,
) sellPriceSyncStats {
	stats := sellPriceSyncStats{
		Unchanged: len(stockRows),
		PriceRows: len(priceRows),
	}
	if len(stockRows) == 0 || len(priceRows) == 0 {
		return stats
	}

	type priceEntry struct {
		ProductName string
		SellPrice   float64
		Normalized  string
		Runes       []rune
	}

	normalizedToPrice := make(map[string]priceEntry, len(priceRows))
	entries := make([]priceEntry, 0, len(priceRows))
	firstRuneIndex := make(map[rune][]int)
	allEntryIndexes := make([]int, 0, len(priceRows))
	for _, row := range priceRows {
		name := strings.TrimSpace(row.ProductName)
		if name == "" {
			continue
		}
		normalized := normalizeProductName(name)
		if normalized == "" {
			continue
		}
		entry := priceEntry{
			ProductName: name,
			SellPrice:   row.Price,
			Normalized:  normalized,
			Runes:       []rune(normalized),
		}
		if _, exists := normalizedToPrice[normalized]; exists {
			stats.DuplicateNameRows++
			continue
		}
		normalizedToPrice[normalized] = entry
		entryIndex := len(entries)
		entries = append(entries, entry)
		allEntryIndexes = append(allEntryIndexes, entryIndex)
		first := firstRune(entry.Runes)
		firstRuneIndex[first] = append(firstRuneIndex[first], entryIndex)
	}
	if len(entries) == 0 {
		return stats
	}

	for idx := range stockRows {
		name := strings.TrimSpace(stockRows[idx].ProductName)
		if name == "" {
			continue
		}
		normalized := normalizeProductName(name)
		if normalized == "" {
			continue
		}
		if exact, ok := normalizedToPrice[normalized]; ok {
			stockRows[idx].SellPrice = exact.SellPrice
			stats.ExactMatched++
			stats.Unchanged--
			continue
		}

		candidateIndexes := firstRuneIndex[firstRune([]rune(normalized))]
		if len(candidateIndexes) == 0 {
			candidateIndexes = allEntryIndexes
		}
		targetRunes := []rune(normalized)
		bestScore := -1.0
		bestDistance := math.MaxInt
		bestSellPrice := 0.0

		for _, candidateIndex := range candidateIndexes {
			entry := entries[candidateIndex]
			score, distance, ok := similarityPercent(
				targetRunes,
				entry.Runes,
				threshold,
			)
			if !ok {
				continue
			}
			if score > bestScore || (score == bestScore && distance < bestDistance) {
				bestScore = score
				bestDistance = distance
				bestSellPrice = entry.SellPrice
			}
		}
		if bestScore >= threshold {
			stockRows[idx].SellPrice = bestSellPrice
			stats.FuzzyMatched++
			stats.Unchanged--
		}
	}

	return stats
}

func normalizeProductName(raw string) string {
	value := strings.TrimSpace(strings.ToLower(raw))
	if value == "" {
		return ""
	}
	replacer := strings.NewReplacer(
		"\u200c", " ", // zwnj
		"\u200f", " ", // rtl mark
		"\u200e", " ", // ltr mark
		"\u064a", "\u06cc", // ي -> ی
		"\u0643", "\u06a9", // ك -> ک
		"\u0629", "\u0647", // ة -> ه
		"،", " ",
		",", " ",
		":", " ",
		";", " ",
		"/", " ",
		"\\", " ",
		"(", " ",
		")", " ",
		"[", " ",
		"]", " ",
		"{", " ",
		"}", " ",
		"-", " ",
		"_", " ",
		"+", " ",
	)
	value = replacer.Replace(value)
	return strings.Join(strings.Fields(value), " ")
}

func firstRune(chars []rune) rune {
	if len(chars) == 0 {
		return rune(0)
	}
	return chars[0]
}

func similarityPercent(
	left []rune,
	right []rune,
	threshold float64,
) (float64, int, bool) {
	maxLen := len(left)
	if len(right) > maxLen {
		maxLen = len(right)
	}
	if maxLen == 0 {
		return 100.0, 0, true
	}
	if threshold >= 100 {
		if string(left) == string(right) {
			return 100.0, 0, true
		}
		return 0, 1, false
	}
	maxDistance := int(math.Floor((100.0 - threshold) * float64(maxLen) / 100.0))
	if maxDistance < 1 {
		maxDistance = 1
	}
	if abs(len(left)-len(right)) > maxDistance {
		return 0, 0, false
	}
	distance, ok := levenshteinWithin(left, right, maxDistance)
	if !ok {
		return 0, distance, false
	}
	score := 100.0 * (1.0 - (float64(distance) / float64(maxLen)))
	return score, distance, score >= threshold
}

func levenshteinWithin(left []rune, right []rune, maxDistance int) (int, bool) {
	leftLen := len(left)
	rightLen := len(right)
	if leftLen == 0 {
		return rightLen, rightLen <= maxDistance
	}
	if rightLen == 0 {
		return leftLen, leftLen <= maxDistance
	}
	if abs(leftLen-rightLen) > maxDistance {
		return maxDistance + 1, false
	}

	prev := make([]int, rightLen+1)
	curr := make([]int, rightLen+1)
	for j := 0; j <= rightLen; j++ {
		prev[j] = j
	}

	for i := 1; i <= leftLen; i++ {
		start := max(1, i-maxDistance)
		end := min(rightLen, i+maxDistance)
		curr[0] = i
		rowMin := curr[0]
		for j := 1; j < start; j++ {
			curr[j] = maxDistance + 1
		}
		for j := start; j <= end; j++ {
			cost := 1
			if left[i-1] == right[j-1] {
				cost = 0
			}
			deletion := prev[j] + 1
			insertion := curr[j-1] + 1
			substitution := prev[j-1] + cost
			curr[j] = min(deletion, min(insertion, substitution))
			if curr[j] < rowMin {
				rowMin = curr[j]
			}
		}
		for j := end + 1; j <= rightLen; j++ {
			curr[j] = maxDistance + 1
		}
		if rowMin > maxDistance {
			return rowMin, false
		}
		prev, curr = curr, prev
	}
	distance := prev[rightLen]
	return distance, distance <= maxDistance
}

func abs(value int) int {
	if value < 0 {
		return -value
	}
	return value
}

func readLegacySQLite(path string) (legacyData, error) {
	admins, err := loadAdmins(path)
	if err != nil {
		return legacyData{}, err
	}
	invoices, err := loadInvoices(path)
	if err != nil {
		return legacyData{}, err
	}
	invoiceLines, err := loadInvoiceLines(path)
	if err != nil {
		return legacyData{}, err
	}
	actions, err := loadActions(path)
	if err != nil {
		return legacyData{}, err
	}
	basalamIDs, err := loadBasalamIDs(path)
	if err != nil {
		return legacyData{}, err
	}

	return legacyData{
		admins:       admins,
		invoices:     invoices,
		invoiceLines: invoiceLines,
		actions:      actions,
		basalamIDs:   basalamIDs,
	}, nil
}

func loadAdmins(path string) ([]legacyAdmin, error) {
	records, err := runSQLiteQuery(path, `
		SELECT username, password_hash, role, auto_lock_minutes, created_at
		FROM admins
		ORDER BY id ASC
	`)
	if err != nil {
		return nil, fmt.Errorf("query sqlite admins: %w", err)
	}
	rows := make([]legacyAdmin, 0, len(records))
	for _, record := range records {
		rows = append(rows, legacyAdmin{
			Username:        strings.TrimSpace(record["username"]),
			PasswordHash:    strings.TrimSpace(record["password_hash"]),
			Role:            strings.TrimSpace(record["role"]),
			AutoLockMinutes: parseInt(record["auto_lock_minutes"]),
			CreatedAt:       strings.TrimSpace(record["created_at"]),
		})
	}
	return rows, nil
}

func loadInvoices(path string) ([]legacyInvoice, error) {
	records, err := runSQLiteQuery(path, `
		SELECT
			id,
			invoice_type,
			created_at,
			total_lines,
			total_qty,
			total_amount,
			invoice_name,
			admin_username
		FROM invoices
		ORDER BY id ASC
	`)
	if err != nil {
		return nil, fmt.Errorf("query sqlite invoices: %w", err)
	}
	rows := make([]legacyInvoice, 0, len(records))
	for _, record := range records {
		rows = append(rows, legacyInvoice{
			ID:            parseInt64(record["id"]),
			InvoiceType:   strings.TrimSpace(record["invoice_type"]),
			CreatedAt:     strings.TrimSpace(record["created_at"]),
			TotalLines:    parseInt(record["total_lines"]),
			TotalQty:      parseInt(record["total_qty"]),
			TotalAmount:   parseFloat(record["total_amount"]),
			InvoiceName:   strings.TrimSpace(record["invoice_name"]),
			AdminUsername: strings.TrimSpace(record["admin_username"]),
		})
	}
	return rows, nil
}

func loadInvoiceLines(path string) ([]legacyInvoiceLine, error) {
	records, err := runSQLiteQuery(path, `
		SELECT
			id,
			invoice_id,
			product_name,
			price,
			quantity,
			line_total,
			cost_price
		FROM invoice_lines
		ORDER BY id ASC
	`)
	if err != nil {
		return nil, fmt.Errorf("query sqlite invoice_lines: %w", err)
	}
	rows := make([]legacyInvoiceLine, 0, len(records))
	for _, record := range records {
		rows = append(rows, legacyInvoiceLine{
			ID:          parseInt64(record["id"]),
			InvoiceID:   parseInt64(record["invoice_id"]),
			ProductName: strings.TrimSpace(record["product_name"]),
			Price:       parseFloat(record["price"]),
			Quantity:    parseInt(record["quantity"]),
			LineTotal:   parseFloat(record["line_total"]),
			CostPrice:   parseFloat(record["cost_price"]),
		})
	}
	return rows, nil
}

func loadActions(path string) ([]legacyAction, error) {
	records, err := runSQLiteQuery(path, `
		SELECT
			id,
			created_at,
			admin_username,
			action_type,
			title,
			details
		FROM actions
		ORDER BY id ASC
	`)
	if err != nil {
		return nil, fmt.Errorf("query sqlite actions: %w", err)
	}
	rows := make([]legacyAction, 0, len(records))
	for _, record := range records {
		rows = append(rows, legacyAction{
			ID:            parseInt64(record["id"]),
			CreatedAt:     strings.TrimSpace(record["created_at"]),
			AdminUsername: strings.TrimSpace(record["admin_username"]),
			ActionType:    strings.TrimSpace(record["action_type"]),
			Title:         strings.TrimSpace(record["title"]),
			Details:       record["details"],
		})
	}
	return rows, nil
}

func loadBasalamIDs(path string) ([]legacyBasalamID, error) {
	records, err := runSQLiteQuery(path, `
		SELECT id, saved_at
		FROM basalam_order_ids
		ORDER BY id ASC
	`)
	if err != nil {
		if strings.Contains(strings.ToLower(err.Error()), "no such table") {
			return []legacyBasalamID{}, nil
		}
		return nil, fmt.Errorf("query sqlite basalam_order_ids: %w", err)
	}
	rows := make([]legacyBasalamID, 0, len(records))
	for _, record := range records {
		rows = append(rows, legacyBasalamID{
			ID:      strings.TrimSpace(record["id"]),
			SavedAt: strings.TrimSpace(record["saved_at"]),
		})
	}
	return rows, nil
}

func runSQLiteQuery(path, query string) ([]map[string]string, error) {
	cmd := exec.Command("sqlite3", "-header", "-csv", path, strings.TrimSpace(query))
	out, err := cmd.CombinedOutput()
	if err != nil {
		return nil, fmt.Errorf("sqlite3 query failed: %s", strings.TrimSpace(string(out)))
	}
	trimmed := strings.TrimSpace(string(out))
	if trimmed == "" {
		return []map[string]string{}, nil
	}

	r := csv.NewReader(bytes.NewBuffer(out))
	r.FieldsPerRecord = -1
	records, err := r.ReadAll()
	if err != nil {
		return nil, fmt.Errorf("parse sqlite csv output: %w", err)
	}
	if len(records) <= 1 {
		return []map[string]string{}, nil
	}

	headers := records[0]
	rows := make([]map[string]string, 0, len(records)-1)
	for _, raw := range records[1:] {
		row := make(map[string]string, len(headers))
		for idx, header := range headers {
			value := ""
			if idx < len(raw) {
				value = raw[idx]
			}
			row[strings.TrimSpace(header)] = value
		}
		rows = append(rows, row)
	}
	return rows, nil
}

func importAll(
	ctx context.Context,
	pool *pgxpool.Pool,
	stockRows []domain.InventoryImportRow,
	legacy legacyData,
	opts options,
) error {
	tx, err := pool.Begin(ctx)
	if err != nil {
		return fmt.Errorf("begin import tx: %w", err)
	}
	defer tx.Rollback(ctx)

	if opts.replace {
		if _, err := tx.Exec(ctx, `
			TRUNCATE TABLE
				invoice_lines,
				invoices,
				actions,
				admins,
				basalam_order_ids,
				stock,
				products
			RESTART IDENTITY CASCADE
		`); err != nil {
			return fmt.Errorf("truncate tables: %w", err)
		}
	}

	if err := upsertStock(ctx, tx, stockRows, opts.syncProducts); err != nil {
		return err
	}
	if err := upsertAdmins(ctx, tx, legacy.admins); err != nil {
		return err
	}
	if err := ensureDefaultAdmin(ctx, tx); err != nil {
		return err
	}
	if err := upsertInvoices(ctx, tx, legacy.invoices); err != nil {
		return err
	}
	if err := upsertInvoiceLines(ctx, tx, legacy.invoiceLines); err != nil {
		return err
	}
	if err := upsertActions(ctx, tx, legacy.actions); err != nil {
		return err
	}
	if err := upsertBasalamIDs(ctx, tx, legacy.basalamIDs); err != nil {
		return err
	}
	if err := syncSequences(ctx, tx); err != nil {
		return err
	}

	if err := tx.Commit(ctx); err != nil {
		return fmt.Errorf("commit import tx: %w", err)
	}
	return nil
}

func upsertStock(
	ctx context.Context,
	tx pgx.Tx,
	rows []domain.InventoryImportRow,
	syncProducts bool,
) error {
	for _, row := range rows {
		name := strings.TrimSpace(row.ProductName)
		if name == "" {
			continue
		}

		if _, err := tx.Exec(ctx, `
			INSERT INTO stock (
				product_name,
				quantity,
				avg_buy_price,
				last_buy_price,
				sell_price,
				alarm,
				source
			) VALUES ($1, $2, $3, $4, $5, $6, $7)
			ON CONFLICT ON CONSTRAINT uq_stock_name_normalized
			DO UPDATE SET
				quantity = EXCLUDED.quantity,
				avg_buy_price = EXCLUDED.avg_buy_price,
				last_buy_price = EXCLUDED.last_buy_price,
				sell_price = EXCLUDED.sell_price,
				alarm = EXCLUDED.alarm,
				source = EXCLUDED.source,
				imported_at = NOW(),
				updated_at = NOW()
		`,
			name,
			row.Quantity,
			row.AvgBuyPrice,
			row.LastBuyPrice,
			row.SellPrice,
			row.Alarm,
			row.Source,
		); err != nil {
			return fmt.Errorf("upsert stock %q: %w", name, err)
		}

		if !syncProducts {
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
			ON CONFLICT ON CONSTRAINT uq_products_name_normalized
			DO UPDATE SET
				quantity = EXCLUDED.quantity,
				avg_buy_price = EXCLUDED.avg_buy_price,
				last_buy_price = EXCLUDED.last_buy_price,
				sell_price = EXCLUDED.sell_price,
				alarm = EXCLUDED.alarm,
				source = EXCLUDED.source,
				updated_at = NOW()
		`,
			name,
			row.Quantity,
			row.AvgBuyPrice,
			row.LastBuyPrice,
			row.SellPrice,
			row.Alarm,
			row.Source,
		); err != nil {
			return fmt.Errorf("upsert product %q from stock: %w", name, err)
		}
	}
	return nil
}

func upsertAdmins(ctx context.Context, tx pgx.Tx, rows []legacyAdmin) error {
	for _, row := range rows {
		username := strings.TrimSpace(row.Username)
		password := strings.TrimSpace(row.PasswordHash)
		role := strings.TrimSpace(row.Role)
		createdAt := normalizeTimestamp(row.CreatedAt)
		if username == "" || password == "" || role == "" {
			continue
		}
		autoLock := row.AutoLockMinutes
		if autoLock <= 0 {
			autoLock = 1
		}
		if _, err := tx.Exec(ctx, `
			INSERT INTO admins (
				username,
				password,
				role,
				auto_lock_minutes,
				created_at
			) VALUES ($1, $2, $3, $4, $5::timestamptz)
			ON CONFLICT (username)
			DO UPDATE SET
				password = EXCLUDED.password,
				role = EXCLUDED.role,
				auto_lock_minutes = EXCLUDED.auto_lock_minutes,
				created_at = EXCLUDED.created_at
		`,
			username,
			password,
			role,
			autoLock,
			createdAt,
		); err != nil {
			return fmt.Errorf("upsert admin %q: %w", username, err)
		}
	}
	return nil
}

func ensureDefaultAdmin(ctx context.Context, tx pgx.Tx) error {
	// Legacy sqlite stores hashed passwords that are not compatible with the
	// current backend's plain-text check; force a known bootstrap credential.
	if _, err := tx.Exec(ctx, `
		INSERT INTO admins (
			username,
			password,
			role,
			auto_lock_minutes,
			created_at
		) VALUES ('reza', 'reza1375', 'manager', 1, NOW())
		ON CONFLICT (username)
		DO UPDATE SET
			password = EXCLUDED.password,
			role = EXCLUDED.role
	`); err != nil {
		return fmt.Errorf("ensure default admin: %w", err)
	}
	return nil
}

func upsertInvoices(ctx context.Context, tx pgx.Tx, rows []legacyInvoice) error {
	for _, row := range rows {
		createdAt := normalizeTimestamp(row.CreatedAt)
		if row.ID <= 0 || strings.TrimSpace(row.InvoiceType) == "" {
			continue
		}
		if _, err := tx.Exec(ctx, `
			INSERT INTO invoices (
				id,
				invoice_type,
				created_at,
				total_lines,
				total_qty,
				total_amount,
				invoice_name,
				admin_username,
				metadata
			) VALUES ($1, $2, $3::timestamptz, $4, $5, $6, $7, $8, '{}'::jsonb)
			ON CONFLICT (id)
			DO UPDATE SET
				invoice_type = EXCLUDED.invoice_type,
				created_at = EXCLUDED.created_at,
				total_lines = EXCLUDED.total_lines,
				total_qty = EXCLUDED.total_qty,
				total_amount = EXCLUDED.total_amount,
				invoice_name = EXCLUDED.invoice_name,
				admin_username = EXCLUDED.admin_username
		`,
			row.ID,
			strings.TrimSpace(row.InvoiceType),
			createdAt,
			row.TotalLines,
			row.TotalQty,
			row.TotalAmount,
			nullableText(row.InvoiceName),
			nullableText(row.AdminUsername),
		); err != nil {
			return fmt.Errorf("upsert invoice id=%d: %w", row.ID, err)
		}
	}
	return nil
}

func upsertInvoiceLines(
	ctx context.Context,
	tx pgx.Tx,
	rows []legacyInvoiceLine,
) error {
	for _, row := range rows {
		if row.ID <= 0 || row.InvoiceID <= 0 {
			continue
		}
		if strings.TrimSpace(row.ProductName) == "" {
			continue
		}
		if _, err := tx.Exec(ctx, `
			INSERT INTO invoice_lines (
				id,
				invoice_id,
				product_name,
				price,
				quantity,
				line_total,
				cost_price
			) VALUES ($1, $2, $3, $4, $5, $6, $7)
			ON CONFLICT (id)
			DO UPDATE SET
				invoice_id = EXCLUDED.invoice_id,
				product_name = EXCLUDED.product_name,
				price = EXCLUDED.price,
				quantity = EXCLUDED.quantity,
				line_total = EXCLUDED.line_total,
				cost_price = EXCLUDED.cost_price
		`,
			row.ID,
			row.InvoiceID,
			strings.TrimSpace(row.ProductName),
			row.Price,
			row.Quantity,
			row.LineTotal,
			row.CostPrice,
		); err != nil {
			return fmt.Errorf("upsert invoice_line id=%d: %w", row.ID, err)
		}
	}
	return nil
}

func upsertActions(ctx context.Context, tx pgx.Tx, rows []legacyAction) error {
	for _, row := range rows {
		createdAt := normalizeTimestamp(row.CreatedAt)
		if row.ID <= 0 {
			continue
		}
		actionType := strings.TrimSpace(row.ActionType)
		title := strings.TrimSpace(row.Title)
		if actionType == "" || title == "" {
			continue
		}
		details := row.Details
		if strings.TrimSpace(details) == "" {
			details = "-"
		}

		if _, err := tx.Exec(ctx, `
			INSERT INTO actions (
				id,
				created_at,
				admin_username,
				action_type,
				title,
				details
			) VALUES ($1, $2::timestamptz, $3, $4, $5, $6)
			ON CONFLICT (id)
			DO UPDATE SET
				created_at = EXCLUDED.created_at,
				admin_username = EXCLUDED.admin_username,
				action_type = EXCLUDED.action_type,
				title = EXCLUDED.title,
				details = EXCLUDED.details
		`,
			row.ID,
			createdAt,
			nullableText(row.AdminUsername),
			actionType,
			title,
			details,
		); err != nil {
			return fmt.Errorf("upsert action id=%d: %w", row.ID, err)
		}
	}
	return nil
}

func upsertBasalamIDs(
	ctx context.Context,
	tx pgx.Tx,
	rows []legacyBasalamID,
) error {
	for _, row := range rows {
		id := strings.TrimSpace(row.ID)
		if id == "" {
			continue
		}
		savedAt := normalizeTimestamp(row.SavedAt)
		if _, err := tx.Exec(ctx, `
			INSERT INTO basalam_order_ids (id, saved_at)
			VALUES ($1, $2::timestamptz)
			ON CONFLICT (id)
			DO UPDATE SET saved_at = EXCLUDED.saved_at
		`, id, savedAt); err != nil {
			return fmt.Errorf("upsert basalam_order_id %q: %w", id, err)
		}
	}
	return nil
}

func syncSequences(ctx context.Context, tx pgx.Tx) error {
	tables := []string{"invoices", "invoice_lines", "actions"}
	for _, table := range tables {
		query := fmt.Sprintf(`
			SELECT setval(
				pg_get_serial_sequence('%s', 'id'),
				COALESCE((SELECT MAX(id) FROM %s), 0) + 1,
				false
			)
		`, table, table)
		if _, err := tx.Exec(ctx, query); err != nil {
			return fmt.Errorf("sync sequence for %s: %w", table, err)
		}
	}
	return nil
}

func nullableText(value string) any {
	trimmed := strings.TrimSpace(value)
	if trimmed == "" {
		return nil
	}
	return trimmed
}

func parseInt(raw string) int {
	value := strings.TrimSpace(raw)
	if value == "" {
		return 0
	}
	n, err := strconv.Atoi(value)
	if err == nil {
		return n
	}
	f, err := strconv.ParseFloat(value, 64)
	if err != nil {
		return 0
	}
	return int(f)
}

func parseInt64(raw string) int64 {
	value := strings.TrimSpace(raw)
	if value == "" {
		return 0
	}
	n, err := strconv.ParseInt(value, 10, 64)
	if err == nil {
		return n
	}
	f, err := strconv.ParseFloat(value, 64)
	if err != nil {
		return 0
	}
	return int64(f)
}

func parseFloat(raw string) float64 {
	value := strings.TrimSpace(strings.ReplaceAll(raw, ",", ""))
	if value == "" {
		return 0
	}
	f, err := strconv.ParseFloat(value, 64)
	if err != nil {
		return 0
	}
	return f
}

func normalizeTimestamp(raw string) string {
	value := strings.TrimSpace(raw)
	if value == "" {
		return time.Now().Format(time.RFC3339)
	}
	if _, err := time.Parse(time.RFC3339Nano, value); err == nil {
		return value
	}
	layouts := []string{
		"2006-01-02 15:04:05",
		"2006-01-02 15:04:05-07:00",
		"2006-01-02T15:04:05",
	}
	for _, layout := range layouts {
		parsed, err := time.Parse(layout, value)
		if err == nil {
			return parsed.Format(time.RFC3339)
		}
	}
	return value
}

func init() {
	if _, err := exec.LookPath("sqlite3"); err != nil {
		log.Fatal(errors.New("sqlite3 command is required for legacy import"))
	}
}
