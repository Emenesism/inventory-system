package domain

import "time"

type Product struct {
	ID           int64     `json:"id"`
	ProductName  string    `json:"product_name"`
	Quantity     int       `json:"quantity"`
	AvgBuyPrice  float64   `json:"avg_buy_price"`
	LastBuyPrice float64   `json:"last_buy_price"`
	SellPrice    float64   `json:"sell_price"`
	Alarm        *int      `json:"alarm,omitempty"`
	Source       *string   `json:"source,omitempty"`
	CreatedAt    time.Time `json:"created_at"`
	UpdatedAt    time.Time `json:"updated_at"`
}

type Invoice struct {
	ID             int64                 `json:"id"`
	InvoiceType    string                `json:"invoice_type"`
	CreatedAt      time.Time             `json:"created_at"`
	TotalLines     int                   `json:"total_lines"`
	TotalQty       int                   `json:"total_qty"`
	TotalAmount    float64               `json:"total_amount"`
	InvoiceName    *string               `json:"invoice_name,omitempty"`
	AdminUsername  *string               `json:"admin_username,omitempty"`
	ProductMatches []InvoiceProductMatch `json:"product_matches,omitempty"`
}

type InvoiceProductMatch struct {
	RowNumber   int     `json:"row_number"`
	ProductName string  `json:"product_name"`
	Price       float64 `json:"price"`
	Quantity    int     `json:"quantity"`
	LineTotal   float64 `json:"line_total"`
	CostPrice   float64 `json:"cost_price"`
}

type InvoiceLine struct {
	ID          int64   `json:"id"`
	InvoiceID   int64   `json:"invoice_id"`
	ProductName string  `json:"product_name"`
	Price       float64 `json:"price"`
	Quantity    int     `json:"quantity"`
	LineTotal   float64 `json:"line_total"`
	CostPrice   float64 `json:"cost_price"`
}

type MonthlySummary struct {
	Month         string  `json:"month"`
	PurchaseTotal float64 `json:"purchase_total"`
	SalesTotal    float64 `json:"sales_total"`
	Profit        float64 `json:"profit"`
	InvoiceCount  int     `json:"invoice_count"`
}

type MonthlyQuantitySummary struct {
	Month            string `json:"month"`
	SalesQty         int    `json:"sales_qty"`
	PurchaseQty      int    `json:"purchase_qty"`
	NetQty           int    `json:"net_qty"`
	SalesInvoices    int    `json:"sales_invoices"`
	PurchaseInvoices int    `json:"purchase_invoices"`
}

type TopSoldProduct struct {
	ProductName  string     `json:"product_name"`
	SoldQty      int        `json:"sold_qty"`
	InvoiceCount int        `json:"invoice_count"`
	LastSoldAt   *time.Time `json:"last_sold_at,omitempty"`
}

type UnsoldProduct struct {
	ProductName string    `json:"product_name"`
	Quantity    int       `json:"quantity"`
	AvgBuyPrice float64   `json:"avg_buy_price"`
	SellPrice   float64   `json:"sell_price"`
	Source      *string   `json:"source,omitempty"`
	UpdatedAt   time.Time `json:"updated_at"`
}

type PurchaseLineInput struct {
	ProductName string  `json:"product_name"`
	Price       float64 `json:"price"`
	Quantity    int     `json:"quantity"`
}

type SalesLineInput struct {
	ProductName string  `json:"product_name"`
	Price       float64 `json:"price"`
	Quantity    int     `json:"quantity"`
}

type InventoryImportRow struct {
	ProductName  string  `json:"product_name"`
	Quantity     int     `json:"quantity"`
	AvgBuyPrice  float64 `json:"avg_buy_price"`
	LastBuyPrice float64 `json:"last_buy_price"`
	SellPrice    float64 `json:"sell_price"`
	Alarm        *int    `json:"alarm,omitempty"`
	Source       *string `json:"source,omitempty"`
}

type InventorySyncResult struct {
	Upserted int `json:"upserted"`
	Deleted  int `json:"deleted"`
}

type ProductPriceRow struct {
	ProductName string  `json:"product_name"`
	Price       float64 `json:"price"`
}

type SellPriceImportResult struct {
	TotalRows       int      `json:"total_rows"`
	MatchedRows     int      `json:"matched_rows"`
	UpdatedProducts int      `json:"updated_products"`
	UnmatchedCount  int      `json:"unmatched_count"`
	UnmatchedNames  []string `json:"unmatched_names,omitempty"`
}

type LowStockRow struct {
	ProductName string  `json:"product_name"`
	Quantity    int     `json:"quantity"`
	Alarm       int     `json:"alarm"`
	Needed      int     `json:"needed"`
	AvgBuyPrice float64 `json:"avg_buy_price"`
	SellPrice   float64 `json:"sell_price"`
	Source      *string `json:"source,omitempty"`
}

type ProductRenameResult struct {
	UpdatedLines      int     `json:"updated_lines"`
	UpdatedInvoiceIDs []int64 `json:"updated_invoice_ids"`
}

type ActionEntry struct {
	ActionID      int64     `json:"action_id"`
	CreatedAt     time.Time `json:"created_at"`
	AdminUsername *string   `json:"admin_username,omitempty"`
	ActionType    string    `json:"action_type"`
	Title         string    `json:"title"`
	Details       string    `json:"details"`
}

type AdminUser struct {
	AdminID         int64  `json:"admin_id"`
	Username        string `json:"username"`
	Role            string `json:"role"`
	AutoLockMinutes int    `json:"auto_lock_minutes"`
}

type SalesPreviewRow struct {
	ProductName  string  `json:"product_name"`
	QuantitySold int     `json:"quantity_sold"`
	SellPrice    float64 `json:"sell_price"`
	CostPrice    float64 `json:"cost_price"`
	Status       string  `json:"status"`
	Message      string  `json:"message"`
	ResolvedName string  `json:"resolved_name"`
}
