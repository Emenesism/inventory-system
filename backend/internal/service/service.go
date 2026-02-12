package service

import (
	"context"
	"fmt"
	"strings"
	"time"

	"backend/internal/domain"
	"backend/internal/repository"
)

type Service struct {
	repo *repository.Repository
}

func New(repo *repository.Repository) *Service {
	return &Service{repo: repo}
}

func (s *Service) ListProducts(ctx context.Context, search string, limit, offset int, threshold *int) ([]domain.Product, error) {
	return s.repo.ListProducts(ctx, repository.ProductListFilter{
		Search:    search,
		Limit:     limit,
		Offset:    offset,
		Threshold: threshold,
	})
}

func (s *Service) GetProduct(ctx context.Context, id int64) (*domain.Product, error) {
	return s.repo.GetProductByID(ctx, id)
}

func (s *Service) CreateProduct(ctx context.Context, input repository.ProductCreateInput) (domain.Product, error) {
	input.ProductName = strings.TrimSpace(input.ProductName)
	if input.ProductName == "" {
		return domain.Product{}, fmt.Errorf("product_name is required")
	}
	return s.repo.CreateProduct(ctx, input)
}

func (s *Service) PatchProduct(ctx context.Context, id int64, input repository.ProductPatchInput) (*domain.Product, error) {
	return s.repo.PatchProduct(ctx, id, input)
}

func (s *Service) DeleteProduct(ctx context.Context, id int64) error {
	return s.repo.DeleteProduct(ctx, id)
}

func (s *Service) ImportInventory(ctx context.Context, rows []domain.InventoryImportRow) (int, int, error) {
	if len(rows) == 0 {
		return 0, 0, fmt.Errorf("import file has no data rows")
	}
	return s.repo.UpsertInventoryRows(ctx, rows)
}

func (s *Service) ReplaceInventory(ctx context.Context, rows []domain.InventoryImportRow) error {
	if len(rows) == 0 {
		return fmt.Errorf("inventory rows are required")
	}
	return s.repo.ReplaceInventory(ctx, rows)
}

func (s *Service) InventorySummary(ctx context.Context) (repository.InventorySummary, error) {
	return s.repo.GetInventorySummary(ctx)
}

func (s *Service) LowStock(ctx context.Context, threshold int) ([]domain.LowStockRow, error) {
	return s.repo.GetLowStock(ctx, threshold)
}

func (s *Service) CreatePurchaseInvoice(
	ctx context.Context,
	invoiceName *string,
	adminUsername *string,
	lines []domain.PurchaseLineInput,
) (int64, error) {
	return s.repo.CreatePurchaseInvoice(ctx, normalizeNullable(invoiceName), normalizeNullable(adminUsername), lines)
}

func (s *Service) CreateSalesInvoice(
	ctx context.Context,
	invoiceName *string,
	adminUsername *string,
	invoiceType string,
	lines []domain.SalesLineInput,
) (int64, error) {
	invoiceType = strings.TrimSpace(invoiceType)
	if invoiceType == "" {
		invoiceType = "sales"
	}
	return s.repo.CreateSalesInvoice(ctx, normalizeNullable(invoiceName), normalizeNullable(adminUsername), invoiceType, lines)
}

func (s *Service) ListInvoices(
	ctx context.Context,
	invoiceType string,
	from, to *time.Time,
	limit, offset int,
) ([]domain.Invoice, error) {
	return s.repo.ListInvoices(ctx, repository.InvoiceListFilter{
		InvoiceType: strings.TrimSpace(invoiceType),
		From:        from,
		To:          to,
		Limit:       limit,
		Offset:      offset,
	})
}

func (s *Service) GetInvoice(ctx context.Context, id int64) (*domain.Invoice, error) {
	return s.repo.GetInvoice(ctx, id)
}

func (s *Service) GetInvoiceLines(ctx context.Context, invoiceID int64) ([]domain.InvoiceLine, error) {
	return s.repo.GetInvoiceLines(ctx, invoiceID)
}

func (s *Service) UpdateInvoiceName(ctx context.Context, id int64, invoiceName *string) error {
	return s.repo.UpdateInvoiceName(ctx, id, normalizeNullable(invoiceName))
}

func (s *Service) UpdateInvoiceLines(
	ctx context.Context,
	id int64,
	invoiceName *string,
	lines []domain.InvoiceLine,
) error {
	return s.repo.UpdateInvoiceLinesReconciled(ctx, id, normalizeNullable(invoiceName), lines)
}

func (s *Service) DeleteInvoice(ctx context.Context, id int64) error {
	return s.repo.DeleteInvoiceReconciled(ctx, id)
}

func (s *Service) MonthlySummary(ctx context.Context, limit int) ([]domain.MonthlySummary, error) {
	return s.repo.GetMonthlySummary(ctx, limit)
}

func (s *Service) InvoiceStats(ctx context.Context) (int, float64, error) {
	return s.repo.GetInvoiceStats(ctx)
}

func (s *Service) ListInvoicesBetween(
	ctx context.Context,
	start time.Time,
	end time.Time,
	productFilter string,
	fuzzy bool,
	idFrom *int64,
	idTo *int64,
) ([]domain.Invoice, error) {
	return s.repo.ListInvoicesBetween(ctx, start, end, strings.TrimSpace(productFilter), fuzzy, idFrom, idTo)
}

func (s *Service) RenameInvoiceProducts(
	ctx context.Context,
	changes [][2]string,
) (domain.ProductRenameResult, error) {
	return s.repo.RenameInvoiceProducts(ctx, changes)
}

func (s *Service) EnsureDefaultAdmin(ctx context.Context) error {
	return s.repo.SetDefaultAdmin(ctx)
}

func (s *Service) AuthenticateAdmin(ctx context.Context, username, password string) (*domain.AdminUser, error) {
	return s.repo.AuthenticateAdmin(ctx, username, password)
}

func (s *Service) ListAdmins(ctx context.Context) ([]domain.AdminUser, error) {
	return s.repo.ListAdmins(ctx)
}

func (s *Service) CreateAdmin(
	ctx context.Context,
	username, password, role string,
	autoLockMinutes int,
) (*domain.AdminUser, error) {
	return s.repo.CreateAdmin(ctx, username, password, role, autoLockMinutes)
}

func (s *Service) UpdateAdminPassword(ctx context.Context, adminID int64, password string) error {
	return s.repo.UpdateAdminPassword(ctx, adminID, password)
}

func (s *Service) UpdateAdminAutoLock(ctx context.Context, adminID int64, minutes int) error {
	return s.repo.UpdateAdminAutoLock(ctx, adminID, minutes)
}

func (s *Service) DeleteAdmin(ctx context.Context, adminID int64) error {
	return s.repo.DeleteAdmin(ctx, adminID)
}

func (s *Service) GetAdminByID(ctx context.Context, adminID int64) (*domain.AdminUser, error) {
	return s.repo.GetAdminByID(ctx, adminID)
}

func (s *Service) LogAction(
	ctx context.Context,
	actionType, title, details string,
	adminUsername *string,
) error {
	return s.repo.LogAction(ctx, actionType, title, details, normalizeNullable(adminUsername))
}

func (s *Service) ListActions(
	ctx context.Context,
	limit, offset int,
	search string,
) ([]domain.ActionEntry, error) {
	return s.repo.ListActions(ctx, limit, offset, search)
}

func (s *Service) CountActions(ctx context.Context, search string) (int, error) {
	return s.repo.CountActions(ctx, search)
}

func (s *Service) PreviewSales(
	ctx context.Context,
	rows []domain.SalesPreviewRow,
) ([]domain.SalesPreviewRow, int, int, error) {
	return s.repo.PreviewSales(ctx, rows)
}

func (s *Service) FetchExistingBasalamIDs(
	ctx context.Context,
	ids []string,
) ([]string, error) {
	return s.repo.FetchExistingBasalamIDs(ctx, ids)
}

func (s *Service) StoreBasalamIDs(
	ctx context.Context,
	ids []string,
) (int, error) {
	return s.repo.StoreBasalamIDs(ctx, ids)
}

func normalizeNullable(value *string) *string {
	if value == nil {
		return nil
	}
	v := strings.TrimSpace(*value)
	if v == "" {
		return nil
	}
	return &v
}
