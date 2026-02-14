# Reza Management Backend (Go + PostgreSQL)

Standalone backend API for VPS hosting.

## Stack
- Go 1.25+
- PostgreSQL 14+
- HTTP router: chi
- DB driver: pgx
- Excel import: excelize

## Run locally
```bash
cd backend
cp .env.example .env
# edit .env with your PostgreSQL credentials
go mod tidy
go run ./cmd/server
```

Config source:
- Backend reads only from `backend/.env` (it does not use exported shell/system vars).
- Required key: `DATABASE_URL`
- Optional key: `PORT` (default `8080`)

Default admin is auto-created on first run:
- username: `reza`
- password: `reza1375`

## API overview
- `GET /healthz`
- `GET /api/v1/products`
- `GET /api/v1/products/{id}`
- `POST /api/v1/products`
- `PATCH /api/v1/products/{id}`
- `DELETE /api/v1/products/{id}`
- `GET /api/v1/inventory/summary`
- `GET /api/v1/inventory/low-stock`
- `POST /api/v1/inventory/import-excel` (multipart field: `file`)
- `POST /api/v1/inventory/replace`
- `POST /api/v1/invoices/purchase`
- `POST /api/v1/invoices/sales`
- `GET /api/v1/invoices`
- `GET /api/v1/invoices/range`
- `GET /api/v1/invoices/stats`
- `GET /api/v1/invoices/{id}`
- `PATCH /api/v1/invoices/{id}/lines`
- `PATCH /api/v1/invoices/{id}/name`
- `DELETE /api/v1/invoices/{id}`
- `POST /api/v1/invoices/rename-products`
- `GET /api/v1/analytics/monthly`
- `POST /api/v1/sales/preview`
- `POST /api/v1/basalam/order-ids/check`
- `POST /api/v1/basalam/order-ids/store`
- `POST /api/v1/admins/authenticate`
- `GET /api/v1/admins`
- `POST /api/v1/admins`
- `PATCH /api/v1/admins/{id}/password`
- `PATCH /api/v1/admins/{id}/auto-lock`
- `DELETE /api/v1/admins/{id}`
- `POST /api/v1/actions`
- `GET /api/v1/actions`
- `GET /api/v1/actions/count`

## Excel import to PostgreSQL
Use this endpoint to migrate from `stock.xlsx` (or excel converted from `stock.dat`) into DB:

```bash
curl -X POST \
  -F "file=@/path/to/stock.xlsx" \
  http://127.0.0.1:8080/api/v1/inventory/import-excel
```

Supported columns (English/Persian aliases):
- `product_name`
- `quantity`
- `avg_buy_price`
- optional: `last_buy_price`, `sell_price`, `alarm`, `source`

## One-shot legacy import script (stock.xlsx + invoices.db)
For repeatable migrations from old local files into PostgreSQL:

```bash
cd backend
./scripts/import_legacy_data.sh
```

What it does:
- runs DB migrations (including `stock` table creation)
- imports all rows from `../stock.xlsx` into `stock`
- also syncs `products` from `stock.xlsx` (enabled by default)
- imports legacy tables from `../invoices.db`:
  - `admins`
  - `invoices`
  - `invoice_lines`
  - `actions`
  - `basalam_order_ids`

Default mode in wrapper script is `--replace` (truncate + reload).

Direct command (custom paths/options):

```bash
cd backend
go run ./cmd/import_legacy \
  --stock /path/to/stock.xlsx \
  --sqlite /path/to/invoices.db \
  --replace
```

## VPS deploy (simple)
1. Install Go and PostgreSQL.
2. Create DB/user and create `backend/.env`.
3. Build binary:
```bash
cd backend
go build -o reza-backend ./cmd/server
```
4. Run with systemd.

Example `/etc/systemd/system/reza-backend.service`:
```ini
[Unit]
Description=Reza Management Backend
After=network.target

[Service]
Type=simple
WorkingDirectory=/opt/reza_management/backend
ExecStart=/opt/reza_management/backend/reza-backend
Restart=always
RestartSec=3
User=www-data

[Install]
WantedBy=multi-user.target
```

Then:
```bash
sudo systemctl daemon-reload
sudo systemctl enable --now reza-backend
sudo systemctl status reza-backend
```
