package repository

import (
	"context"
	"fmt"
	"strings"
)

func (r *Repository) FetchExistingBasalamIDs(
	ctx context.Context,
	ids []string,
) ([]string, error) {
	if len(ids) == 0 {
		return []string{}, nil
	}
	clean := make([]string, 0, len(ids))
	for _, id := range ids {
		value := strings.TrimSpace(id)
		if value == "" {
			continue
		}
		clean = append(clean, value)
	}
	if len(clean) == 0 {
		return []string{}, nil
	}

	rows, err := r.pool.Query(ctx, `
		SELECT id
		FROM basalam_order_ids
		WHERE id = ANY($1)
	`, clean)
	if err != nil {
		return nil, fmt.Errorf("fetch existing basalam ids: %w", err)
	}
	defer rows.Close()

	existing := make([]string, 0)
	for rows.Next() {
		var id string
		if err := rows.Scan(&id); err != nil {
			return nil, fmt.Errorf("scan existing basalam id: %w", err)
		}
		existing = append(existing, id)
	}
	if err := rows.Err(); err != nil {
		return nil, fmt.Errorf("iterate existing basalam ids: %w", err)
	}
	return existing, nil
}

func (r *Repository) StoreBasalamIDs(ctx context.Context, ids []string) (int, error) {
	if len(ids) == 0 {
		return 0, nil
	}
	clean := make([]string, 0, len(ids))
	seen := map[string]struct{}{}
	for _, id := range ids {
		value := strings.TrimSpace(id)
		if value == "" {
			continue
		}
		if _, exists := seen[value]; exists {
			continue
		}
		seen[value] = struct{}{}
		clean = append(clean, value)
	}
	if len(clean) == 0 {
		return 0, nil
	}

	tx, err := r.pool.Begin(ctx)
	if err != nil {
		return 0, fmt.Errorf("begin store basalam ids tx: %w", err)
	}
	defer tx.Rollback(ctx)

	inserted := 0
	for _, id := range clean {
		cmd, err := tx.Exec(ctx, `
			INSERT INTO basalam_order_ids (id)
			VALUES ($1)
			ON CONFLICT (id) DO NOTHING
		`, id)
		if err != nil {
			return 0, fmt.Errorf("insert basalam id %q: %w", id, err)
		}
		inserted += int(cmd.RowsAffected())
	}

	if err := tx.Commit(ctx); err != nil {
		return 0, fmt.Errorf("commit store basalam ids tx: %w", err)
	}
	return inserted, nil
}
