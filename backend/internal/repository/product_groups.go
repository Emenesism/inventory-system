package repository

import (
	"context"
	"fmt"
	"strings"

	"backend/internal/domain"

	"github.com/jackc/pgx/v5"
)

func (r *Repository) ListProductGroups(ctx context.Context) ([]domain.ProductGroup, error) {
	rows, err := r.pool.Query(ctx, `
		SELECT
			g.id,
			g.name,
			p.id,
			p.product_name
		FROM product_groups g
		LEFT JOIN product_group_members gm ON gm.group_id = g.id
		LEFT JOIN products p ON p.id = gm.product_id
		ORDER BY g.name ASC, g.id ASC, p.product_name ASC
	`)
	if err != nil {
		return nil, fmt.Errorf("list product groups: %w", err)
	}
	defer rows.Close()
	return scanProductGroups(rows)
}

func (r *Repository) CreateProductGroup(
	ctx context.Context,
	name string,
) (domain.ProductGroup, error) {
	cleanName, err := validateProductGroupName(name)
	if err != nil {
		return domain.ProductGroup{}, err
	}
	var exists bool
	if err := r.pool.QueryRow(ctx, `
		SELECT EXISTS(
			SELECT 1
			FROM product_groups
			WHERE LOWER(name) = LOWER($1)
		)
	`, cleanName).Scan(&exists); err != nil {
		return domain.ProductGroup{}, fmt.Errorf("check product group name: %w", err)
	}
	if exists {
		return domain.ProductGroup{}, fmt.Errorf("group name already exists: %s", cleanName)
	}

	var groupID int64
	if err := r.pool.QueryRow(ctx, `
		INSERT INTO product_groups (name, updated_at)
		VALUES ($1, NOW())
		RETURNING id
	`, cleanName).Scan(&groupID); err != nil {
		return domain.ProductGroup{}, fmt.Errorf("create product group: %w", err)
	}
	return r.getProductGroup(ctx, groupID)
}

func (r *Repository) UpdateProductGroup(
	ctx context.Context,
	groupID int64,
	name *string,
	members *[]string,
) (domain.ProductGroup, error) {
	tx, err := r.pool.Begin(ctx)
	if err != nil {
		return domain.ProductGroup{}, fmt.Errorf("begin product group update tx: %w", err)
	}
	defer tx.Rollback(ctx)

	var currentName string
	if err := tx.QueryRow(ctx, `
		SELECT name
		FROM product_groups
		WHERE id = $1
		FOR UPDATE
	`, groupID).Scan(&currentName); err != nil {
		if err == pgx.ErrNoRows {
			return domain.ProductGroup{}, ErrNotFound
		}
		return domain.ProductGroup{}, fmt.Errorf("load product group %d: %w", groupID, err)
	}

	if name != nil {
		cleanName, nameErr := validateProductGroupName(*name)
		if nameErr != nil {
			return domain.ProductGroup{}, nameErr
		}
		var exists bool
		if err := tx.QueryRow(ctx, `
			SELECT EXISTS(
				SELECT 1
				FROM product_groups
				WHERE LOWER(name) = LOWER($1)
				  AND id <> $2
			)
		`, cleanName, groupID).Scan(&exists); err != nil {
			return domain.ProductGroup{}, fmt.Errorf("check product group name: %w", err)
		}
		if exists {
			return domain.ProductGroup{}, fmt.Errorf("group name already exists: %s", cleanName)
		}
		if _, err := tx.Exec(ctx, `
			UPDATE product_groups
			SET name = $2, updated_at = NOW()
			WHERE id = $1
		`, groupID, cleanName); err != nil {
			return domain.ProductGroup{}, fmt.Errorf("update product group name: %w", err)
		}
	}

	if members != nil {
		resolvedMembers, membersErr := resolveProductGroupMembersTx(ctx, tx, *members)
		if membersErr != nil {
			return domain.ProductGroup{}, membersErr
		}
		if conflictErr := ensureMembersAvailableForGroupTx(ctx, tx, groupID, resolvedMembers); conflictErr != nil {
			return domain.ProductGroup{}, conflictErr
		}
		if err := replaceProductGroupMembersTx(ctx, tx, groupID, resolvedMembers); err != nil {
			return domain.ProductGroup{}, err
		}
	}

	group, err := getProductGroupTx(ctx, tx, groupID)
	if err != nil {
		return domain.ProductGroup{}, err
	}
	if err := tx.Commit(ctx); err != nil {
		return domain.ProductGroup{}, fmt.Errorf("commit product group update tx: %w", err)
	}
	return group, nil
}

func (r *Repository) DeleteProductGroup(ctx context.Context, groupID int64) error {
	commandTag, err := r.pool.Exec(ctx, `
		DELETE FROM product_groups
		WHERE id = $1
	`, groupID)
	if err != nil {
		return fmt.Errorf("delete product group %d: %w", groupID, err)
	}
	if commandTag.RowsAffected() == 0 {
		return ErrNotFound
	}
	return nil
}

func validateProductGroupName(name string) (string, error) {
	cleanName := strings.TrimSpace(name)
	if cleanName == "" {
		return "", fmt.Errorf("group name is required")
	}
	return cleanName, nil
}

func resolveProductGroupMembersTx(
	ctx context.Context,
	tx pgx.Tx,
	names []string,
) ([]domain.ProductGroupMember, error) {
	seen := map[string]struct{}{}
	result := make([]domain.ProductGroupMember, 0, len(names))
	for _, rawName := range names {
		name := strings.TrimSpace(rawName)
		if name == "" {
			continue
		}
		key := normalizeName(name)
		if _, exists := seen[key]; exists {
			continue
		}
		seen[key] = struct{}{}

		var member domain.ProductGroupMember
		if err := tx.QueryRow(ctx, `
			SELECT id, product_name
			FROM products
			WHERE LOWER(product_name) = LOWER($1)
		`, name).Scan(&member.ProductID, &member.ProductName); err != nil {
			if err == pgx.ErrNoRows {
				return nil, fmt.Errorf("product not found in inventory: %s", name)
			}
			return nil, fmt.Errorf("load product %q for group: %w", name, err)
		}
		result = append(result, member)
	}
	return result, nil
}

func ensureMembersAvailableForGroupTx(
	ctx context.Context,
	tx pgx.Tx,
	groupID int64,
	members []domain.ProductGroupMember,
) error {
	if len(members) == 0 {
		return nil
	}
	productIDs := make([]int64, 0, len(members))
	for _, member := range members {
		productIDs = append(productIDs, member.ProductID)
	}
	var (
		productName string
		groupName   string
	)
	err := tx.QueryRow(ctx, `
		SELECT
			p.product_name,
			g.name
		FROM product_group_members gm
		JOIN product_groups g ON g.id = gm.group_id
		JOIN products p ON p.id = gm.product_id
		WHERE gm.product_id = ANY($1)
		  AND gm.group_id <> $2
		ORDER BY p.product_name ASC
		LIMIT 1
	`, productIDs, groupID).Scan(&productName, &groupName)
	if err == pgx.ErrNoRows {
		return nil
	}
	if err != nil {
		return fmt.Errorf("check product group conflicts: %w", err)
	}
	return fmt.Errorf("product %s already belongs to group %s", productName, groupName)
}

func replaceProductGroupMembersTx(
	ctx context.Context,
	tx pgx.Tx,
	groupID int64,
	members []domain.ProductGroupMember,
) error {
	if _, err := tx.Exec(ctx, `
		DELETE FROM product_group_members
		WHERE group_id = $1
	`, groupID); err != nil {
		return fmt.Errorf("clear product group members: %w", err)
	}
	for _, member := range members {
		if _, err := tx.Exec(ctx, `
			INSERT INTO product_group_members (group_id, product_id)
			VALUES ($1, $2)
		`, groupID, member.ProductID); err != nil {
			return fmt.Errorf("insert product group member %q: %w", member.ProductName, err)
		}
	}
	if _, err := tx.Exec(ctx, `
		UPDATE product_groups
		SET updated_at = NOW()
		WHERE id = $1
	`, groupID); err != nil {
		return fmt.Errorf("touch product group %d: %w", groupID, err)
	}
	return nil
}

func (r *Repository) getProductGroup(
	ctx context.Context,
	groupID int64,
) (domain.ProductGroup, error) {
	rows, err := r.pool.Query(ctx, `
		SELECT
			g.id,
			g.name,
			p.id,
			p.product_name
		FROM product_groups g
		LEFT JOIN product_group_members gm ON gm.group_id = g.id
		LEFT JOIN products p ON p.id = gm.product_id
		WHERE g.id = $1
		ORDER BY p.product_name ASC
	`, groupID)
	if err != nil {
		return domain.ProductGroup{}, fmt.Errorf("query product group %d: %w", groupID, err)
	}
	defer rows.Close()
	items, err := scanProductGroups(rows)
	if err != nil {
		return domain.ProductGroup{}, err
	}
	if len(items) == 0 {
		return domain.ProductGroup{}, ErrNotFound
	}
	return items[0], nil
}

func getProductGroupTx(
	ctx context.Context,
	tx pgx.Tx,
	groupID int64,
) (domain.ProductGroup, error) {
	rows, err := tx.Query(ctx, `
		SELECT
			g.id,
			g.name,
			p.id,
			p.product_name
		FROM product_groups g
		LEFT JOIN product_group_members gm ON gm.group_id = g.id
		LEFT JOIN products p ON p.id = gm.product_id
		WHERE g.id = $1
		ORDER BY p.product_name ASC
	`, groupID)
	if err != nil {
		return domain.ProductGroup{}, fmt.Errorf("query product group %d: %w", groupID, err)
	}
	defer rows.Close()
	items, err := scanProductGroups(rows)
	if err != nil {
		return domain.ProductGroup{}, err
	}
	if len(items) == 0 {
		return domain.ProductGroup{}, ErrNotFound
	}
	return items[0], nil
}

func scanProductGroups(rows pgx.Rows) ([]domain.ProductGroup, error) {
	items := make([]domain.ProductGroup, 0)
	groupIndex := map[int64]int{}
	for rows.Next() {
		var (
			groupID     int64
			groupName   string
			productID   *int64
			productName *string
		)
		if err := rows.Scan(&groupID, &groupName, &productID, &productName); err != nil {
			return nil, fmt.Errorf("scan product groups: %w", err)
		}
		idx, exists := groupIndex[groupID]
		if !exists {
			idx = len(items)
			groupIndex[groupID] = idx
			items = append(items, domain.ProductGroup{
				GroupID: groupID,
				Name:    groupName,
				Members: []domain.ProductGroupMember{},
			})
		}
		if productID != nil && productName != nil {
			items[idx].Members = append(items[idx].Members, domain.ProductGroupMember{
				ProductID:   *productID,
				ProductName: *productName,
			})
		}
	}
	if err := rows.Err(); err != nil {
		return nil, fmt.Errorf("iterate product groups: %w", err)
	}
	return items, nil
}

func resolveGroupedProductsTx(
	ctx context.Context,
	tx pgx.Tx,
	productID int64,
) ([]domain.ProductGroupMember, error) {
	rows, err := tx.Query(ctx, `
		SELECT DISTINCT
			p.id,
			p.product_name
		FROM products p
		WHERE p.id = $1
		UNION
		SELECT DISTINCT
			p2.id,
			p2.product_name
		FROM product_group_members base_member
		JOIN product_group_members group_member
			ON group_member.group_id = base_member.group_id
		JOIN products p2
			ON p2.id = group_member.product_id
		WHERE base_member.product_id = $1
		ORDER BY product_name ASC
	`, productID)
	if err != nil {
		return nil, fmt.Errorf("resolve grouped products for %d: %w", productID, err)
	}
	defer rows.Close()

	result := make([]domain.ProductGroupMember, 0)
	for rows.Next() {
		var member domain.ProductGroupMember
		if err := rows.Scan(&member.ProductID, &member.ProductName); err != nil {
			return nil, fmt.Errorf("scan grouped product for %d: %w", productID, err)
		}
		result = append(result, member)
	}
	if err := rows.Err(); err != nil {
		return nil, fmt.Errorf("iterate grouped products for %d: %w", productID, err)
	}
	return result, nil
}
