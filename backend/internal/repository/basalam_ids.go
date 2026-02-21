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

	inserted := 0
	if err := r.pool.QueryRow(ctx, `
		WITH inserted AS (
			INSERT INTO basalam_order_ids (id)
			SELECT DISTINCT value
			FROM unnest($1::text[]) AS value
			WHERE value <> ''
			ON CONFLICT (id) DO NOTHING
			RETURNING 1
		)
		SELECT COUNT(*)::int FROM inserted
	`, clean).Scan(&inserted); err != nil {
		return 0, fmt.Errorf("store basalam ids: %w", err)
	}
	return inserted, nil
}
