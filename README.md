# Armkala Inventory Suite
Website: `armkala.ir`

## Professional Summary
Armala Inventory Suite is a production-grade desktop application for
inventory, purchasing, sales import, and operational analytics. It is built
in Python with a PySide6 UI layer, emphasizes data integrity, and favors
transparent workflows (preview before apply, explicit exports, auditable logs).

## Core Competencies
- Inventory lifecycle management with inline edits and validation
- Sales ingestion from Excel/CSV with preview and safe apply
- Purchase invoice workflow with weighted average cost updates
- Invoice management: visible factor IDs, edit purchases, delete sales with stock reconciliation
- Batch factor export with Jalali date range + optional product filter (per-invoice sheets)
- Low-stock intelligence with export-ready reporting
- Basalam order retrieval and targeted filtering
- Action audit trail with manager-only access
- Centralized logging and diagnostics

## Technical Stack
- UI: PySide6 (Qt)
- Data: pandas + openpyxl
- Fuzzy matching: rapidfuzz
- HTTP: requests
- Storage: local Excel/CSV + JSON config + log files

## Architecture Highlights
- Layered structure: UI pages, controllers, services, and utilities
- Stateless services where possible; state centralized in UI and config
- Defensive input handling (preview, validation, error dialogs)
- Rotating log files for traceability

## Key Modules (Selected)
- Inventory: load/save and inline edits
- Sales Import: preview, validate, and apply with summary feedback
- Purchase Invoice: invoice entry and stock cost recalculation
- Invoices: delete sales invoices, edit purchase invoices, and export per-invoice Excel
- Factor Export: batch export to one workbook (sheet per invoice ID)
- Analytics: trends and profitability views
- Low Stock: thresholds and export-ready list
- Basalam Orders:
  - Vendor ID is fixed to 563284
  - Paginates with limit=30 until completion
  - Uses tab=COMPLECTED (API enum spelling)
  - Filters to status: "وضعیت سفارش = رضایت مشتری"
  - Exports RTL Excel with Persian headers
  - Includes item properties: size, color, model, plate type, font, stitch color,
    cover side model, sole material
  - Product name is expanded with property title/value pairs

## Audit Trail (Actions)
- Logs admin activity such as inventory edits, invoice imports/edits/deletes, exports,
  Basalam fetches/exports, password changes, and login/logout
- Actions page is visible to managers; employees see a blurred view

## Configuration
`config.json` fields:
- `inventory_file` (path)
- `backend_url` (Go backend base URL, default `http://127.0.0.1:8080`)
- `theme` (`light` or `dark`)
- `low_stock_threshold` (int)
- `access_token` (Basalam API token)

## Observability
- Logs at `logs/app.log`
- UI exposes logs under Reports/Logs and the Actions audit trail

## Runbook (Windows)
```bash
python -m venv .venv
.\.venv\Scripts\activate
pip install -r requirements.txt
python -m app.main
```

## Operating Notes
- Inventory file must include: `product_name`, `quantity`, `avg_buy_price`.
- Basalam fetch requires `access_token` in `config.json`.
- Excel exports are RTL/Persian and auto-fit columns.

## Backend (Go + PostgreSQL)
- A standalone backend service is available in `backend/`.
- See `backend/README.md` for API, migration, and VPS deployment instructions.
- UI now reads/writes app data through backend APIs (inventory, invoices, admins, actions, low-stock, Basalam ID store).
