package http

import (
	"net/http"

	"github.com/go-chi/chi/v5"
	"github.com/go-chi/chi/v5/middleware"
)

func NewRouter(handler *Handler) http.Handler {
	r := chi.NewRouter()
	r.Use(middleware.RealIP)
	r.Use(Logger)
	r.Use(Recoverer)
	r.Use(Timeout)
	r.Use(CORS)

	r.Get("/healthz", handler.Health)

	r.Route("/api/v1", func(r chi.Router) {
		r.Get("/products", handler.ListProducts)
		r.Get("/products/{id}", handler.GetProduct)
		r.Post("/products", handler.CreateProduct)
		r.Patch("/products/{id}", handler.PatchProduct)
		r.Delete("/products/{id}", handler.DeleteProduct)

		r.Get("/inventory/summary", handler.InventorySummary)
		r.Get("/inventory/low-stock", handler.LowStock)
		r.Post("/inventory/import-excel", handler.ImportInventoryExcel)
		r.Post("/inventory/import-sell-prices", handler.ImportSellPrices)
		r.Post("/inventory/replace", handler.ReplaceInventory)
		r.Post("/inventory/sync", handler.SyncInventory)
		r.Get("/settings/sell-price-alarm", handler.GetSellPriceAlarmPercent)
		r.Patch("/settings/sell-price-alarm", handler.UpdateSellPriceAlarmPercent)

		r.Get("/invoices", handler.ListInvoices)
		r.Get("/invoices/range", handler.ListInvoicesBetween)
		r.Get("/invoices/stats", handler.InvoiceStats)
		r.Get("/invoices/{id}", handler.GetInvoice)
		r.Delete("/invoices/{id}", handler.DeleteInvoice)
		r.Patch("/invoices/{id}/name", handler.UpdateInvoiceName)
		r.Patch("/invoices/{id}/lines", handler.UpdateInvoiceLines)
		r.Post("/invoices/purchase", handler.CreatePurchaseInvoice)
		r.Post("/invoices/sales", handler.CreateSalesInvoice)
		r.Post("/invoices/rename-products", handler.RenameProducts)

		r.Get("/analytics/monthly", handler.MonthlySummary)
		r.Get("/analytics/monthly-qty", handler.MonthlyQuantitySummary)
		r.Get("/analytics/top-products", handler.TopSoldProducts)
		r.Get("/analytics/unsold-products", handler.UnsoldProducts)
		r.Post("/sales/preview", handler.SalesPreview)
		r.Post("/basalam/order-ids/check", handler.BasalamCheckExistingIDs)
		r.Post("/basalam/order-ids/store", handler.BasalamStoreIDs)

		r.Post("/admins/authenticate", handler.AuthenticateAdmin)
		r.Get("/admins", handler.ListAdmins)
		r.Post("/admins", handler.CreateAdmin)
		r.Get("/admins/{id}", handler.GetAdmin)
		r.Patch("/admins/{id}/password", handler.UpdateAdminPassword)
		r.Patch("/admins/{id}/auto-lock", handler.UpdateAdminAutoLock)
		r.Delete("/admins/{id}", handler.DeleteAdmin)

		r.Post("/actions", handler.LogAction)
		r.Get("/actions", handler.ListActions)
		r.Get("/actions/count", handler.CountActions)
	})

	return r
}
