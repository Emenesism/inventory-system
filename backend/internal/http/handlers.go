package http

import (
	"encoding/json"
	"errors"
	"fmt"
	"net/http"
	"strconv"
	"strings"
	"time"

	"backend/internal/domain"
	"backend/internal/excel"
	"backend/internal/repository"
	"backend/internal/service"

	"github.com/go-chi/chi/v5"
)

type Handler struct {
	svc *service.Service
}

type inventoryProductView struct {
	ProductName  string  `json:"product_name"`
	Quantity     int     `json:"quantity"`
	AvgBuyPrice  float64 `json:"avg_buy_price"`
	LastBuyPrice float64 `json:"last_buy_price"`
	SellPrice    float64 `json:"sell_price"`
	Alarm        *int    `json:"alarm,omitempty"`
	Source       *string `json:"source,omitempty"`
}

func NewHandler(svc *service.Service) *Handler {
	return &Handler{svc: svc}
}

func (h *Handler) Health(w http.ResponseWriter, _ *http.Request) {
	writeJSON(w, http.StatusOK, map[string]any{"status": "ok"})
}

func (h *Handler) ListProducts(w http.ResponseWriter, r *http.Request) {
	query := r.URL.Query()
	limit, err := parseOptionalInt(query.Get("limit"), 200)
	if err != nil {
		writeError(w, http.StatusBadRequest, err.Error())
		return
	}
	offset, err := parseOptionalInt(query.Get("offset"), 0)
	if err != nil {
		writeError(w, http.StatusBadRequest, err.Error())
		return
	}

	var threshold *int
	if lowStockRaw := strings.TrimSpace(query.Get("low_stock")); lowStockRaw != "" {
		lowStock, err := strconv.ParseBool(lowStockRaw)
		if err != nil {
			writeError(w, http.StatusBadRequest, "low_stock must be true or false")
			return
		}
		if lowStock {
			value, err := parseOptionalInt(query.Get("threshold"), 5)
			if err != nil {
				writeError(w, http.StatusBadRequest, err.Error())
				return
			}
			threshold = &value
		}
	}

	items, err := h.svc.ListProducts(r.Context(), query.Get("search"), limit, offset, threshold)
	if err != nil {
		writeError(w, http.StatusInternalServerError, err.Error())
		return
	}
	if strings.EqualFold(strings.TrimSpace(query.Get("view")), "inventory") {
		leanItems := make([]inventoryProductView, 0, len(items))
		for _, item := range items {
			leanItems = append(leanItems, inventoryProductView{
				ProductName:  item.ProductName,
				Quantity:     item.Quantity,
				AvgBuyPrice:  item.AvgBuyPrice,
				LastBuyPrice: item.LastBuyPrice,
				SellPrice:    item.SellPrice,
				Alarm:        item.Alarm,
				Source:       item.Source,
			})
		}
		writeJSON(
			w,
			http.StatusOK,
			map[string]any{"items": leanItems, "count": len(leanItems)},
		)
		return
	}
	writeJSON(w, http.StatusOK, map[string]any{"items": items, "count": len(items)})
}

func (h *Handler) GetProduct(w http.ResponseWriter, r *http.Request) {
	id, err := parseID(chi.URLParam(r, "id"))
	if err != nil {
		writeError(w, http.StatusBadRequest, err.Error())
		return
	}
	product, err := h.svc.GetProduct(r.Context(), id)
	if err != nil {
		if errors.Is(err, repository.ErrNotFound) {
			writeError(w, http.StatusNotFound, "product not found")
			return
		}
		writeError(w, http.StatusInternalServerError, err.Error())
		return
	}
	writeJSON(w, http.StatusOK, product)
}

type createProductRequest struct {
	ProductName  string  `json:"product_name"`
	Quantity     int     `json:"quantity"`
	AvgBuyPrice  float64 `json:"avg_buy_price"`
	LastBuyPrice float64 `json:"last_buy_price"`
	SellPrice    float64 `json:"sell_price"`
	Alarm        *int    `json:"alarm"`
	Source       *string `json:"source"`
}

func (h *Handler) CreateProduct(w http.ResponseWriter, r *http.Request) {
	var req createProductRequest
	if err := decodeJSON(r, &req); err != nil {
		writeError(w, http.StatusBadRequest, err.Error())
		return
	}
	if req.LastBuyPrice <= 0 {
		req.LastBuyPrice = req.AvgBuyPrice
	}
	created, err := h.svc.CreateProduct(r.Context(), repository.ProductCreateInput{
		ProductName:  req.ProductName,
		Quantity:     req.Quantity,
		AvgBuyPrice:  req.AvgBuyPrice,
		LastBuyPrice: req.LastBuyPrice,
		SellPrice:    req.SellPrice,
		Alarm:        req.Alarm,
		Source:       req.Source,
	})
	if err != nil {
		writeError(w, http.StatusBadRequest, err.Error())
		return
	}
	writeJSON(w, http.StatusCreated, created)
}

type patchProductRequest struct {
	ProductName  *string  `json:"product_name"`
	Quantity     *int     `json:"quantity"`
	AvgBuyPrice  *float64 `json:"avg_buy_price"`
	LastBuyPrice *float64 `json:"last_buy_price"`
	SellPrice    *float64 `json:"sell_price"`
	Alarm        *int     `json:"alarm"`
	Source       *string  `json:"source"`
}

func (h *Handler) PatchProduct(w http.ResponseWriter, r *http.Request) {
	id, err := parseID(chi.URLParam(r, "id"))
	if err != nil {
		writeError(w, http.StatusBadRequest, err.Error())
		return
	}

	var req patchProductRequest
	if err := decodeJSON(r, &req); err != nil {
		writeError(w, http.StatusBadRequest, err.Error())
		return
	}

	updated, err := h.svc.PatchProduct(r.Context(), id, repository.ProductPatchInput{
		ProductName:  req.ProductName,
		Quantity:     req.Quantity,
		AvgBuyPrice:  req.AvgBuyPrice,
		LastBuyPrice: req.LastBuyPrice,
		SellPrice:    req.SellPrice,
		Alarm:        req.Alarm,
		Source:       req.Source,
	})
	if err != nil {
		if errors.Is(err, repository.ErrNotFound) {
			writeError(w, http.StatusNotFound, "product not found")
			return
		}
		writeError(w, http.StatusBadRequest, err.Error())
		return
	}
	writeJSON(w, http.StatusOK, updated)
}

func (h *Handler) DeleteProduct(w http.ResponseWriter, r *http.Request) {
	id, err := parseID(chi.URLParam(r, "id"))
	if err != nil {
		writeError(w, http.StatusBadRequest, err.Error())
		return
	}
	if err := h.svc.DeleteProduct(r.Context(), id); err != nil {
		if errors.Is(err, repository.ErrNotFound) {
			writeError(w, http.StatusNotFound, "product not found")
			return
		}
		writeError(w, http.StatusInternalServerError, err.Error())
		return
	}
	w.WriteHeader(http.StatusNoContent)
}

func (h *Handler) InventorySummary(w http.ResponseWriter, r *http.Request) {
	summary, err := h.svc.InventorySummary(r.Context())
	if err != nil {
		writeError(w, http.StatusInternalServerError, err.Error())
		return
	}
	writeJSON(w, http.StatusOK, summary)
}

func (h *Handler) LowStock(w http.ResponseWriter, r *http.Request) {
	threshold, err := parseOptionalInt(r.URL.Query().Get("threshold"), 5)
	if err != nil {
		writeError(w, http.StatusBadRequest, err.Error())
		return
	}
	rows, err := h.svc.LowStock(r.Context(), threshold)
	if err != nil {
		writeError(w, http.StatusInternalServerError, err.Error())
		return
	}
	writeJSON(w, http.StatusOK, map[string]any{"items": rows, "count": len(rows)})
}

func (h *Handler) ImportInventoryExcel(w http.ResponseWriter, r *http.Request) {
	if err := r.ParseMultipartForm(32 << 20); err != nil {
		writeError(w, http.StatusBadRequest, "failed to parse multipart form")
		return
	}
	file, header, err := r.FormFile("file")
	if err != nil {
		writeError(w, http.StatusBadRequest, "file field is required")
		return
	}
	defer file.Close()

	rows, err := excel.ParseInventoryRows(file)
	if err != nil {
		writeError(w, http.StatusBadRequest, err.Error())
		return
	}

	created, updated, err := h.svc.ImportInventory(r.Context(), rows)
	if err != nil {
		writeError(w, http.StatusBadRequest, err.Error())
		return
	}

	writeJSON(w, http.StatusOK, map[string]any{
		"file_name":  header.Filename,
		"total_rows": len(rows),
		"created":    created,
		"updated":    updated,
	})
}

func (h *Handler) ImportSellPrices(w http.ResponseWriter, r *http.Request) {
	if err := r.ParseMultipartForm(32 << 20); err != nil {
		writeError(w, http.StatusBadRequest, "failed to parse multipart form")
		return
	}
	file, header, err := r.FormFile("file")
	if err != nil {
		writeError(w, http.StatusBadRequest, "file field is required")
		return
	}
	defer file.Close()

	rows, detectedFormat, err := excel.ParseProductPriceRows(header.Filename, file)
	if err != nil {
		writeError(w, http.StatusBadRequest, err.Error())
		return
	}

	result, err := h.svc.ImportSellPrices(r.Context(), rows)
	if err != nil {
		writeError(w, http.StatusBadRequest, err.Error())
		return
	}

	writeJSON(w, http.StatusOK, map[string]any{
		"file_name":        header.Filename,
		"detected_format":  detectedFormat,
		"total_rows":       result.TotalRows,
		"matched_rows":     result.MatchedRows,
		"updated_products": result.UpdatedProducts,
		"unmatched_count":  result.UnmatchedCount,
		"unmatched_names":  result.UnmatchedNames,
	})
}

func (h *Handler) GetSellPriceAlarmPercent(w http.ResponseWriter, r *http.Request) {
	percent, err := h.svc.GetSellPriceAlarmPercent(r.Context())
	if err != nil {
		writeError(w, http.StatusInternalServerError, err.Error())
		return
	}
	writeJSON(w, http.StatusOK, map[string]any{
		"percent": percent,
	})
}

type updateSellPriceAlarmPercentRequest struct {
	Percent float64 `json:"percent"`
}

func (h *Handler) UpdateSellPriceAlarmPercent(w http.ResponseWriter, r *http.Request) {
	var req updateSellPriceAlarmPercentRequest
	if err := decodeJSON(r, &req); err != nil {
		writeError(w, http.StatusBadRequest, err.Error())
		return
	}
	percent, err := h.svc.SetSellPriceAlarmPercent(r.Context(), req.Percent)
	if err != nil {
		writeError(w, http.StatusBadRequest, err.Error())
		return
	}
	writeJSON(w, http.StatusOK, map[string]any{
		"percent": percent,
	})
}

type replaceInventoryRequest struct {
	Rows []domain.InventoryImportRow `json:"rows"`
}

func (h *Handler) ReplaceInventory(w http.ResponseWriter, r *http.Request) {
	var req replaceInventoryRequest
	if err := decodeJSON(r, &req); err != nil {
		writeError(w, http.StatusBadRequest, err.Error())
		return
	}
	if len(req.Rows) == 0 {
		writeError(w, http.StatusBadRequest, "rows are required")
		return
	}
	if err := h.svc.ReplaceInventory(r.Context(), req.Rows); err != nil {
		writeError(w, http.StatusBadRequest, err.Error())
		return
	}
	writeJSON(w, http.StatusOK, map[string]any{"replaced": len(req.Rows)})
}

type syncInventoryRequest struct {
	Upserts []domain.InventoryImportRow `json:"upserts"`
	Deletes []string                    `json:"deletes"`
}

func (h *Handler) SyncInventory(w http.ResponseWriter, r *http.Request) {
	var req syncInventoryRequest
	if err := decodeJSON(r, &req); err != nil {
		writeError(w, http.StatusBadRequest, err.Error())
		return
	}
	if len(req.Upserts) == 0 && len(req.Deletes) == 0 {
		writeError(w, http.StatusBadRequest, "upserts or deletes are required")
		return
	}
	result, err := h.svc.SyncInventory(r.Context(), req.Upserts, req.Deletes)
	if err != nil {
		writeError(w, http.StatusBadRequest, err.Error())
		return
	}
	writeJSON(w, http.StatusOK, map[string]any{
		"upserted": result.Upserted,
		"deleted":  result.Deleted,
	})
}

type createPurchaseInvoiceRequest struct {
	InvoiceName   *string                    `json:"invoice_name"`
	AdminUsername *string                    `json:"admin_username"`
	Lines         []domain.PurchaseLineInput `json:"lines"`
}

func (h *Handler) CreatePurchaseInvoice(w http.ResponseWriter, r *http.Request) {
	var req createPurchaseInvoiceRequest
	if err := decodeJSON(r, &req); err != nil {
		writeError(w, http.StatusBadRequest, err.Error())
		return
	}
	invoiceID, err := h.svc.CreatePurchaseInvoice(r.Context(), req.InvoiceName, req.AdminUsername, req.Lines)
	if err != nil {
		writeError(w, http.StatusBadRequest, err.Error())
		return
	}
	writeJSON(w, http.StatusCreated, map[string]any{"invoice_id": invoiceID})
}

type createSalesInvoiceRequest struct {
	InvoiceName   *string                 `json:"invoice_name"`
	AdminUsername *string                 `json:"admin_username"`
	InvoiceType   string                  `json:"invoice_type"`
	Lines         []domain.SalesLineInput `json:"lines"`
}

func (h *Handler) CreateSalesInvoice(w http.ResponseWriter, r *http.Request) {
	var req createSalesInvoiceRequest
	if err := decodeJSON(r, &req); err != nil {
		writeError(w, http.StatusBadRequest, err.Error())
		return
	}
	invoiceID, err := h.svc.CreateSalesInvoice(r.Context(), req.InvoiceName, req.AdminUsername, req.InvoiceType, req.Lines)
	if err != nil {
		writeError(w, http.StatusBadRequest, err.Error())
		return
	}
	writeJSON(w, http.StatusCreated, map[string]any{"invoice_id": invoiceID})
}

func (h *Handler) ListInvoices(w http.ResponseWriter, r *http.Request) {
	query := r.URL.Query()
	limit, err := parseOptionalInt(query.Get("limit"), 200)
	if err != nil {
		writeError(w, http.StatusBadRequest, err.Error())
		return
	}
	offset, err := parseOptionalInt(query.Get("offset"), 0)
	if err != nil {
		writeError(w, http.StatusBadRequest, err.Error())
		return
	}
	from, err := parseOptionalTime(query.Get("from"))
	if err != nil {
		writeError(w, http.StatusBadRequest, "invalid from date")
		return
	}
	to, err := parseOptionalTime(query.Get("to"))
	if err != nil {
		writeError(w, http.StatusBadRequest, "invalid to date")
		return
	}

	invoices, err := h.svc.ListInvoices(r.Context(), query.Get("type"), from, to, limit, offset)
	if err != nil {
		writeError(w, http.StatusInternalServerError, err.Error())
		return
	}
	totalCount, totalAmount, err := h.svc.InvoiceStats(r.Context(), query.Get("type"))
	if err != nil {
		writeError(w, http.StatusInternalServerError, err.Error())
		return
	}
	writeJSON(w, http.StatusOK, map[string]any{
		"items":        invoices,
		"count":        len(invoices),
		"total_count":  totalCount,
		"total_amount": totalAmount,
	})
}

func (h *Handler) ListInvoicesBetween(w http.ResponseWriter, r *http.Request) {
	query := r.URL.Query()
	start, err := parseRequiredTime(query.Get("start"))
	if err != nil {
		writeError(w, http.StatusBadRequest, "start is required and must be a valid date")
		return
	}
	end, err := parseRequiredTime(query.Get("end"))
	if err != nil {
		writeError(w, http.StatusBadRequest, "end is required and must be a valid date")
		return
	}
	fuzzy := false
	if fuzzyRaw := strings.TrimSpace(query.Get("fuzzy")); fuzzyRaw != "" {
		value, parseErr := strconv.ParseBool(fuzzyRaw)
		if parseErr != nil {
			writeError(w, http.StatusBadRequest, "fuzzy must be true or false")
			return
		}
		fuzzy = value
	}
	idFrom, err := parseOptionalInt64(query.Get("id_from"))
	if err != nil {
		writeError(w, http.StatusBadRequest, err.Error())
		return
	}
	idTo, err := parseOptionalInt64(query.Get("id_to"))
	if err != nil {
		writeError(w, http.StatusBadRequest, err.Error())
		return
	}
	items, err := h.svc.ListInvoicesBetween(
		r.Context(),
		*start,
		*end,
		query.Get("product_filter"),
		fuzzy,
		idFrom,
		idTo,
	)
	if err != nil {
		writeError(w, http.StatusBadRequest, err.Error())
		return
	}
	writeJSON(w, http.StatusOK, map[string]any{"items": items, "count": len(items)})
}

func (h *Handler) GetInvoice(w http.ResponseWriter, r *http.Request) {
	id, err := parseID(chi.URLParam(r, "id"))
	if err != nil {
		writeError(w, http.StatusBadRequest, err.Error())
		return
	}

	invoice, err := h.svc.GetInvoice(r.Context(), id)
	if err != nil {
		if errors.Is(err, repository.ErrNotFound) {
			writeError(w, http.StatusNotFound, "invoice not found")
			return
		}
		writeError(w, http.StatusInternalServerError, err.Error())
		return
	}

	lines, err := h.svc.GetInvoiceLines(r.Context(), id)
	if err != nil {
		writeError(w, http.StatusInternalServerError, err.Error())
		return
	}

	writeJSON(w, http.StatusOK, map[string]any{
		"invoice": invoice,
		"lines":   lines,
	})
}

type updateInvoiceNameRequest struct {
	InvoiceName *string `json:"invoice_name"`
}

func (h *Handler) UpdateInvoiceName(w http.ResponseWriter, r *http.Request) {
	id, err := parseID(chi.URLParam(r, "id"))
	if err != nil {
		writeError(w, http.StatusBadRequest, err.Error())
		return
	}

	var req updateInvoiceNameRequest
	if err := decodeJSON(r, &req); err != nil {
		writeError(w, http.StatusBadRequest, err.Error())
		return
	}
	if err := h.svc.UpdateInvoiceName(r.Context(), id, req.InvoiceName); err != nil {
		if errors.Is(err, repository.ErrNotFound) {
			writeError(w, http.StatusNotFound, "invoice not found")
			return
		}
		writeError(w, http.StatusInternalServerError, err.Error())
		return
	}
	writeJSON(w, http.StatusOK, map[string]any{"invoice_id": id, "updated": true})
}

type updateInvoiceLinesRequest struct {
	InvoiceName *string              `json:"invoice_name"`
	Lines       []domain.InvoiceLine `json:"lines"`
}

func (h *Handler) UpdateInvoiceLines(w http.ResponseWriter, r *http.Request) {
	id, err := parseID(chi.URLParam(r, "id"))
	if err != nil {
		writeError(w, http.StatusBadRequest, err.Error())
		return
	}
	var req updateInvoiceLinesRequest
	if err := decodeJSON(r, &req); err != nil {
		writeError(w, http.StatusBadRequest, err.Error())
		return
	}
	if len(req.Lines) == 0 {
		writeError(w, http.StatusBadRequest, "lines are required")
		return
	}
	if err := h.svc.UpdateInvoiceLines(r.Context(), id, req.InvoiceName, req.Lines); err != nil {
		if errors.Is(err, repository.ErrNotFound) {
			writeError(w, http.StatusNotFound, "invoice not found")
			return
		}
		writeError(w, http.StatusBadRequest, err.Error())
		return
	}
	writeJSON(w, http.StatusOK, map[string]any{"invoice_id": id, "updated": true})
}

func (h *Handler) DeleteInvoice(w http.ResponseWriter, r *http.Request) {
	id, err := parseID(chi.URLParam(r, "id"))
	if err != nil {
		writeError(w, http.StatusBadRequest, err.Error())
		return
	}
	if err := h.svc.DeleteInvoice(r.Context(), id); err != nil {
		if errors.Is(err, repository.ErrNotFound) {
			writeError(w, http.StatusNotFound, "invoice not found")
			return
		}
		writeError(w, http.StatusBadRequest, err.Error())
		return
	}
	w.WriteHeader(http.StatusNoContent)
}

func (h *Handler) InvoiceStats(w http.ResponseWriter, r *http.Request) {
	count, total, err := h.svc.InvoiceStats(
		r.Context(),
		r.URL.Query().Get("type"),
	)
	if err != nil {
		writeError(w, http.StatusInternalServerError, err.Error())
		return
	}
	writeJSON(w, http.StatusOK, map[string]any{
		"count":        count,
		"total_amount": total,
	})
}

type renameProductsRequest struct {
	Changes [][]string `json:"changes"`
}

func (h *Handler) RenameProducts(w http.ResponseWriter, r *http.Request) {
	var req renameProductsRequest
	if err := decodeJSON(r, &req); err != nil {
		writeError(w, http.StatusBadRequest, err.Error())
		return
	}
	changes := make([][2]string, 0, len(req.Changes))
	for _, entry := range req.Changes {
		if len(entry) != 2 {
			continue
		}
		changes = append(changes, [2]string{entry[0], entry[1]})
	}
	result, err := h.svc.RenameInvoiceProducts(r.Context(), changes)
	if err != nil {
		writeError(w, http.StatusBadRequest, err.Error())
		return
	}
	writeJSON(w, http.StatusOK, result)
}

func (h *Handler) MonthlySummary(w http.ResponseWriter, r *http.Request) {
	limit, err := parseOptionalInt(r.URL.Query().Get("limit"), 12)
	if err != nil {
		writeError(w, http.StatusBadRequest, err.Error())
		return
	}
	data, err := h.svc.MonthlySummary(r.Context(), limit)
	if err != nil {
		writeError(w, http.StatusInternalServerError, err.Error())
		return
	}
	writeJSON(w, http.StatusOK, map[string]any{"items": data, "count": len(data)})
}

func (h *Handler) MonthlyQuantitySummary(w http.ResponseWriter, r *http.Request) {
	limit, err := parseOptionalInt(r.URL.Query().Get("limit"), 12)
	if err != nil {
		writeError(w, http.StatusBadRequest, err.Error())
		return
	}
	data, err := h.svc.MonthlyQuantitySummary(r.Context(), limit)
	if err != nil {
		writeError(w, http.StatusInternalServerError, err.Error())
		return
	}
	writeJSON(w, http.StatusOK, map[string]any{"items": data, "count": len(data)})
}

func (h *Handler) TopSoldProducts(w http.ResponseWriter, r *http.Request) {
	days, err := parseOptionalInt(r.URL.Query().Get("days"), 90)
	if err != nil {
		writeError(w, http.StatusBadRequest, err.Error())
		return
	}
	limit, err := parseOptionalInt(r.URL.Query().Get("limit"), 10)
	if err != nil {
		writeError(w, http.StatusBadRequest, err.Error())
		return
	}
	items, err := h.svc.TopSoldProducts(r.Context(), days, limit)
	if err != nil {
		writeError(w, http.StatusInternalServerError, err.Error())
		return
	}
	writeJSON(w, http.StatusOK, map[string]any{"items": items, "count": len(items)})
}

func (h *Handler) UnsoldProducts(w http.ResponseWriter, r *http.Request) {
	days, err := parseOptionalInt(r.URL.Query().Get("days"), 30)
	if err != nil {
		writeError(w, http.StatusBadRequest, err.Error())
		return
	}
	limit, err := parseOptionalInt(r.URL.Query().Get("limit"), 200)
	if err != nil {
		writeError(w, http.StatusBadRequest, err.Error())
		return
	}
	items, err := h.svc.UnsoldProducts(r.Context(), days, limit)
	if err != nil {
		writeError(w, http.StatusInternalServerError, err.Error())
		return
	}
	writeJSON(w, http.StatusOK, map[string]any{"items": items, "count": len(items)})
}

type salesPreviewRequest struct {
	Rows []domain.SalesPreviewRow `json:"rows"`
}

func (h *Handler) SalesPreview(w http.ResponseWriter, r *http.Request) {
	var req salesPreviewRequest
	if err := decodeJSON(r, &req); err != nil {
		writeError(w, http.StatusBadRequest, err.Error())
		return
	}
	rows, successCount, errorCount, err := h.svc.PreviewSales(r.Context(), req.Rows)
	if err != nil {
		writeError(w, http.StatusBadRequest, err.Error())
		return
	}
	writeJSON(w, http.StatusOK, map[string]any{
		"rows": rows,
		"summary": map[string]any{
			"total":   len(rows),
			"success": successCount,
			"errors":  errorCount,
		},
	})
}

type basalamCheckRequest struct {
	IDs []string `json:"ids"`
}

func (h *Handler) BasalamCheckExistingIDs(w http.ResponseWriter, r *http.Request) {
	var req basalamCheckRequest
	if err := decodeJSON(r, &req); err != nil {
		writeError(w, http.StatusBadRequest, err.Error())
		return
	}
	items, err := h.svc.FetchExistingBasalamIDs(r.Context(), req.IDs)
	if err != nil {
		writeError(w, http.StatusBadRequest, err.Error())
		return
	}
	writeJSON(w, http.StatusOK, map[string]any{
		"existing_ids": items,
		"count":        len(items),
	})
}

type basalamStoreRequest struct {
	IDs []string `json:"ids"`
}

func (h *Handler) BasalamStoreIDs(w http.ResponseWriter, r *http.Request) {
	var req basalamStoreRequest
	if err := decodeJSON(r, &req); err != nil {
		writeError(w, http.StatusBadRequest, err.Error())
		return
	}
	inserted, err := h.svc.StoreBasalamIDs(r.Context(), req.IDs)
	if err != nil {
		writeError(w, http.StatusBadRequest, err.Error())
		return
	}
	writeJSON(w, http.StatusOK, map[string]any{
		"inserted": inserted,
	})
}

type authAdminRequest struct {
	Username string `json:"username"`
	Password string `json:"password"`
}

func (h *Handler) AuthenticateAdmin(w http.ResponseWriter, r *http.Request) {
	var req authAdminRequest
	if err := decodeJSON(r, &req); err != nil {
		writeError(w, http.StatusBadRequest, err.Error())
		return
	}
	admin, err := h.svc.AuthenticateAdmin(r.Context(), req.Username, req.Password)
	if err != nil {
		writeError(w, http.StatusInternalServerError, err.Error())
		return
	}
	if admin == nil {
		writeError(w, http.StatusUnauthorized, "invalid username or password")
		return
	}
	writeJSON(w, http.StatusOK, admin)
}

func (h *Handler) ListAdmins(w http.ResponseWriter, r *http.Request) {
	items, err := h.svc.ListAdmins(r.Context())
	if err != nil {
		writeError(w, http.StatusInternalServerError, err.Error())
		return
	}
	writeJSON(w, http.StatusOK, map[string]any{"items": items, "count": len(items)})
}

type createAdminRequest struct {
	Username        string `json:"username"`
	Password        string `json:"password"`
	Role            string `json:"role"`
	AutoLockMinutes int    `json:"auto_lock_minutes"`
}

func (h *Handler) CreateAdmin(w http.ResponseWriter, r *http.Request) {
	var req createAdminRequest
	if err := decodeJSON(r, &req); err != nil {
		writeError(w, http.StatusBadRequest, err.Error())
		return
	}
	admin, err := h.svc.CreateAdmin(r.Context(), req.Username, req.Password, req.Role, req.AutoLockMinutes)
	if err != nil {
		writeError(w, http.StatusBadRequest, err.Error())
		return
	}
	writeJSON(w, http.StatusCreated, admin)
}

func (h *Handler) GetAdmin(w http.ResponseWriter, r *http.Request) {
	id, err := parseID(chi.URLParam(r, "id"))
	if err != nil {
		writeError(w, http.StatusBadRequest, err.Error())
		return
	}
	admin, err := h.svc.GetAdminByID(r.Context(), id)
	if err != nil {
		if errors.Is(err, repository.ErrNotFound) {
			writeError(w, http.StatusNotFound, "admin not found")
			return
		}
		writeError(w, http.StatusInternalServerError, err.Error())
		return
	}
	writeJSON(w, http.StatusOK, admin)
}

type updatePasswordRequest struct {
	Password string `json:"password"`
}

func (h *Handler) UpdateAdminPassword(w http.ResponseWriter, r *http.Request) {
	id, err := parseID(chi.URLParam(r, "id"))
	if err != nil {
		writeError(w, http.StatusBadRequest, err.Error())
		return
	}
	var req updatePasswordRequest
	if err := decodeJSON(r, &req); err != nil {
		writeError(w, http.StatusBadRequest, err.Error())
		return
	}
	if err := h.svc.UpdateAdminPassword(r.Context(), id, req.Password); err != nil {
		if errors.Is(err, repository.ErrNotFound) {
			writeError(w, http.StatusNotFound, "admin not found")
			return
		}
		writeError(w, http.StatusBadRequest, err.Error())
		return
	}
	writeJSON(w, http.StatusOK, map[string]any{"updated": true})
}

type updateAutoLockRequest struct {
	AutoLockMinutes int `json:"auto_lock_minutes"`
}

func (h *Handler) UpdateAdminAutoLock(w http.ResponseWriter, r *http.Request) {
	id, err := parseID(chi.URLParam(r, "id"))
	if err != nil {
		writeError(w, http.StatusBadRequest, err.Error())
		return
	}
	var req updateAutoLockRequest
	if err := decodeJSON(r, &req); err != nil {
		writeError(w, http.StatusBadRequest, err.Error())
		return
	}
	if err := h.svc.UpdateAdminAutoLock(r.Context(), id, req.AutoLockMinutes); err != nil {
		if errors.Is(err, repository.ErrNotFound) {
			writeError(w, http.StatusNotFound, "admin not found")
			return
		}
		writeError(w, http.StatusBadRequest, err.Error())
		return
	}
	writeJSON(w, http.StatusOK, map[string]any{"updated": true})
}

func (h *Handler) DeleteAdmin(w http.ResponseWriter, r *http.Request) {
	id, err := parseID(chi.URLParam(r, "id"))
	if err != nil {
		writeError(w, http.StatusBadRequest, err.Error())
		return
	}
	if err := h.svc.DeleteAdmin(r.Context(), id); err != nil {
		if errors.Is(err, repository.ErrNotFound) {
			writeError(w, http.StatusNotFound, "admin not found")
			return
		}
		writeError(w, http.StatusInternalServerError, err.Error())
		return
	}
	w.WriteHeader(http.StatusNoContent)
}

type logActionRequest struct {
	ActionType    string  `json:"action_type"`
	Title         string  `json:"title"`
	Details       string  `json:"details"`
	AdminUsername *string `json:"admin_username"`
}

func (h *Handler) LogAction(w http.ResponseWriter, r *http.Request) {
	var req logActionRequest
	if err := decodeJSON(r, &req); err != nil {
		writeError(w, http.StatusBadRequest, err.Error())
		return
	}
	if err := h.svc.LogAction(r.Context(), req.ActionType, req.Title, req.Details, req.AdminUsername); err != nil {
		writeError(w, http.StatusBadRequest, err.Error())
		return
	}
	writeJSON(w, http.StatusCreated, map[string]any{"created": true})
}

func (h *Handler) ListActions(w http.ResponseWriter, r *http.Request) {
	query := r.URL.Query()
	limit, err := parseOptionalInt(query.Get("limit"), 200)
	if err != nil {
		writeError(w, http.StatusBadRequest, err.Error())
		return
	}
	offset, err := parseOptionalInt(query.Get("offset"), 0)
	if err != nil {
		writeError(w, http.StatusBadRequest, err.Error())
		return
	}
	items, err := h.svc.ListActions(r.Context(), limit, offset, query.Get("search"))
	if err != nil {
		writeError(w, http.StatusInternalServerError, err.Error())
		return
	}
	writeJSON(w, http.StatusOK, map[string]any{"items": items, "count": len(items)})
}

func (h *Handler) CountActions(w http.ResponseWriter, r *http.Request) {
	count, err := h.svc.CountActions(r.Context(), r.URL.Query().Get("search"))
	if err != nil {
		writeError(w, http.StatusInternalServerError, err.Error())
		return
	}
	writeJSON(w, http.StatusOK, map[string]any{"count": count})
}

func decodeJSON(r *http.Request, out any) error {
	dec := json.NewDecoder(r.Body)
	dec.DisallowUnknownFields()
	if err := dec.Decode(out); err != nil {
		return fmt.Errorf("invalid JSON body")
	}
	return nil
}

func parseOptionalInt(raw string, defaultValue int) (int, error) {
	value := strings.TrimSpace(raw)
	if value == "" {
		return defaultValue, nil
	}
	parsed, err := strconv.Atoi(value)
	if err != nil {
		return 0, fmt.Errorf("invalid integer: %s", raw)
	}
	if parsed < 0 {
		return 0, fmt.Errorf("value cannot be negative")
	}
	return parsed, nil
}

func parseOptionalTime(raw string) (*time.Time, error) {
	value := strings.TrimSpace(raw)
	if value == "" {
		return nil, nil
	}
	for _, layout := range []string{time.RFC3339, "2006-01-02"} {
		if parsed, err := time.Parse(layout, value); err == nil {
			if layout == "2006-01-02" {
				utc := parsed.UTC()
				return &utc, nil
			}
			return &parsed, nil
		}
	}
	return nil, fmt.Errorf("invalid time")
}

func parseRequiredTime(raw string) (*time.Time, error) {
	if strings.TrimSpace(raw) == "" {
		return nil, fmt.Errorf("time is required")
	}
	return parseOptionalTime(raw)
}

func parseOptionalInt64(raw string) (*int64, error) {
	value := strings.TrimSpace(raw)
	if value == "" {
		return nil, nil
	}
	parsed, err := strconv.ParseInt(value, 10, 64)
	if err != nil || parsed <= 0 {
		return nil, fmt.Errorf("invalid id value: %s", raw)
	}
	return &parsed, nil
}

func parseID(raw string) (int64, error) {
	id, err := strconv.ParseInt(strings.TrimSpace(raw), 10, 64)
	if err != nil || id <= 0 {
		return 0, fmt.Errorf("invalid id")
	}
	return id, nil
}

func writeJSON(w http.ResponseWriter, status int, payload any) {
	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(status)
	_ = json.NewEncoder(w).Encode(payload)
}

func writeError(w http.ResponseWriter, status int, message string) {
	writeJSON(w, status, map[string]any{"error": message})
}
