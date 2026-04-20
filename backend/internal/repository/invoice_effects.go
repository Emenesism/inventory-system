package repository

import (
	"context"
	"fmt"
	"sort"

	"github.com/jackc/pgx/v5"
)

type inventoryEffect struct {
	ProductID   int64
	ProductName string
	Quantity    int
	TotalCost   float64
	LastPrice   float64
}

func effectKey(productID int64, productName string) string {
	if productID > 0 {
		return fmt.Sprintf("id:%d", productID)
	}
	return "name:" + normalizeName(productName)
}

func collectEffectKeys(
	oldMap map[string]*inventoryEffect,
	newMap map[string]*inventoryEffect,
) []string {
	set := make(map[string]struct{}, len(oldMap)+len(newMap))
	for key := range oldMap {
		set[key] = struct{}{}
	}
	for key := range newMap {
		set[key] = struct{}{}
	}
	keys := make([]string, 0, len(set))
	for key := range set {
		keys = append(keys, key)
	}
	sort.Strings(keys)
	return keys
}

func aggregateInventoryEffects(
	effects []inventoryEffect,
) map[string]*inventoryEffect {
	result := make(map[string]*inventoryEffect)
	for _, effect := range effects {
		key := effectKey(effect.ProductID, effect.ProductName)
		entry, exists := result[key]
		if !exists {
			entry = &inventoryEffect{
				ProductID:   effect.ProductID,
				ProductName: effect.ProductName,
			}
			result[key] = entry
		}
		if effect.ProductID > 0 {
			entry.ProductID = effect.ProductID
		}
		if effect.ProductName != "" {
			entry.ProductName = effect.ProductName
		}
		entry.Quantity += effect.Quantity
		entry.TotalCost += effect.TotalCost
		if effect.LastPrice > 0 {
			entry.LastPrice = effect.LastPrice
		}
	}
	return result
}

func loadInvoiceStockEffectsTx(
	ctx context.Context,
	tx pgx.Tx,
	invoiceID int64,
) ([]inventoryEffect, error) {
	rows, err := tx.Query(ctx, `
		SELECT
			product_id,
			product_name,
			quantity,
			total_cost::double precision,
			last_price::double precision
		FROM invoice_stock_effects
		WHERE invoice_id = $1
		ORDER BY product_name ASC, product_id ASC
	`, invoiceID)
	if err != nil {
		return nil, fmt.Errorf("query invoice stock effects %d: %w", invoiceID, err)
	}
	defer rows.Close()

	result := make([]inventoryEffect, 0)
	for rows.Next() {
		var effect inventoryEffect
		if err := rows.Scan(
			&effect.ProductID,
			&effect.ProductName,
			&effect.Quantity,
			&effect.TotalCost,
			&effect.LastPrice,
		); err != nil {
			return nil, fmt.Errorf("scan invoice stock effects %d: %w", invoiceID, err)
		}
		result = append(result, effect)
	}
	if err := rows.Err(); err != nil {
		return nil, fmt.Errorf("iterate invoice stock effects %d: %w", invoiceID, err)
	}
	return result, nil
}

func replaceInvoiceStockEffectsTx(
	ctx context.Context,
	tx pgx.Tx,
	invoiceID int64,
	effects []inventoryEffect,
) error {
	if _, err := tx.Exec(ctx, `
		DELETE FROM invoice_stock_effects
		WHERE invoice_id = $1
	`, invoiceID); err != nil {
		return fmt.Errorf("clear invoice stock effects: %w", err)
	}
	for _, effect := range effects {
		if effect.Quantity == 0 {
			continue
		}
		if _, err := tx.Exec(ctx, `
			INSERT INTO invoice_stock_effects (
				invoice_id,
				product_id,
				product_name,
				quantity,
				total_cost,
				last_price
			) VALUES ($1, $2, $3, $4, $5, $6)
		`, invoiceID, effect.ProductID, effect.ProductName, effect.Quantity, effect.TotalCost, effect.LastPrice); err != nil {
			return fmt.Errorf("insert invoice stock effect for invoice %d: %w", invoiceID, err)
		}
	}
	return nil
}

func loadProductForEffectUpdate(
	ctx context.Context,
	tx pgx.Tx,
	effect inventoryEffect,
) (int64, string, int, float64, float64, error) {
	var (
		id          int64
		productName string
		quantity    int
		avgBuy      float64
		lastBuy     float64
	)
	if effect.ProductID > 0 {
		err := tx.QueryRow(ctx, `
			SELECT
				id,
				product_name,
				quantity,
				avg_buy_price::double precision,
				last_buy_price::double precision
			FROM products
			WHERE id = $1
			FOR UPDATE
		`, effect.ProductID).Scan(&id, &productName, &quantity, &avgBuy, &lastBuy)
		if err == nil {
			return id, productName, quantity, avgBuy, lastBuy, nil
		}
		if err != pgx.ErrNoRows {
			return 0, "", 0, 0, 0, fmt.Errorf("load product %d: %w", effect.ProductID, err)
		}
	}
	id, quantity, avgBuy, lastBuy, err := loadProductForUpdate(ctx, tx, effect.ProductName)
	if err != nil {
		return 0, "", 0, 0, 0, err
	}
	return id, effect.ProductName, quantity, avgBuy, lastBuy, nil
}

func applySalesChangeTx(
	ctx context.Context,
	tx pgx.Tx,
	oldEffects []inventoryEffect,
	newEffects []inventoryEffect,
) error {
	oldMap := aggregateInventoryEffects(oldEffects)
	newMap := aggregateInventoryEffects(newEffects)
	keys := collectEffectKeys(oldMap, newMap)

	for _, key := range keys {
		oldQty := 0
		newQty := 0
		effect := inventoryEffect{}
		if oldEntry := oldMap[key]; oldEntry != nil {
			oldQty = oldEntry.Quantity
			effect = *oldEntry
		}
		if newEntry := newMap[key]; newEntry != nil {
			newQty = newEntry.Quantity
			effect = *newEntry
		}
		delta := oldQty - newQty
		if delta == 0 {
			continue
		}

		productID, productName, currentQty, _, _, err := loadProductForEffectUpdate(ctx, tx, effect)
		if err == ErrNotFound {
			return fmt.Errorf("product not found in inventory: %s", effect.ProductName)
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
			return fmt.Errorf("update sales product %s: %w", productName, err)
		}
	}
	return nil
}

func applyPurchaseChangeTx(
	ctx context.Context,
	tx pgx.Tx,
	oldEffects []inventoryEffect,
	newEffects []inventoryEffect,
) error {
	oldMap := aggregateInventoryEffects(oldEffects)
	newMap := aggregateInventoryEffects(newEffects)
	keys := collectEffectKeys(oldMap, newMap)

	for _, key := range keys {
		oldQty := 0
		oldCost := 0.0
		newQty := 0
		newCost := 0.0
		newLastPrice := 0.0
		effect := inventoryEffect{}
		if oldEntry := oldMap[key]; oldEntry != nil {
			oldQty = oldEntry.Quantity
			oldCost = oldEntry.TotalCost
			effect = *oldEntry
		}
		if newEntry := newMap[key]; newEntry != nil {
			newQty = newEntry.Quantity
			newCost = newEntry.TotalCost
			newLastPrice = newEntry.LastPrice
			effect = *newEntry
		}

		productID, productName, currentQty, currentAvg, currentLast, err := loadProductForEffectUpdate(ctx, tx, effect)
		if err == ErrNotFound {
			return fmt.Errorf("product not found in inventory: %s", effect.ProductName)
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
			return fmt.Errorf("update purchase product %s: %w", productName, err)
		}
	}
	return nil
}
