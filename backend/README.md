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
- Backend reads environment variables first (`DATABASE_URL`, `PORT`).
- If an env var is missing, backend falls back to `backend/.env`.
- Required key: `DATABASE_URL`
- Optional key: `PORT` (default `8080`)

Default admin is auto-created on first run:
- username: `reza`
- password: `reza1375`

## API overview
- `GET /healthz`
- `GET /api/v1/products`
  - Optional query: `view=inventory` returns only inventory page fields
- `GET /api/v1/products/{id}`
- `POST /api/v1/products`
- `PATCH /api/v1/products/{id}`
- `DELETE /api/v1/products/{id}`
- `GET /api/v1/inventory/summary`
- `GET /api/v1/inventory/low-stock`
- `POST /api/v1/inventory/import-excel` (multipart field: `file`)
- `POST /api/v1/inventory/replace`
- `POST /api/v1/inventory/sync` (`upserts` + `deletes`)
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
  http://127.0.0.1:1234/api/v1/inventory/import-excel
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

This wrapper auto-falls back to Docker if local `go>=1.25` and `sqlite3` are not available.

Docker-only entrypoint (explicit):

```bash
cd backend
./scripts/import_legacy_data_docker.sh
```

Notes:
- requires Docker on the server
- default Docker network mode is `host` (best for `DATABASE_URL=...@127.0.0.1:5432/...`)
- override network mode if needed: `IMPORT_DOCKER_NETWORK_MODE=bridge ./scripts/import_legacy_data_docker.sh`

What it does:
- runs DB migrations (including `stock` table creation)
- imports all rows from `../stock.xlsx` into `stock`
- also syncs `products` from `stock.xlsx` (enabled by default)
- if `../pro_clean_with_price.xlsx` exists, maps `sell_price` by product name:
  - exact normalized match first
  - fuzzy match with similarity `>= 96%` as fallback
- imports legacy tables from `../invoices.db`:
  - `admins`
  - `invoices`
  - `invoice_lines`
  - `actions`
  - `basalam_order_ids`

Default mode in wrapper script is `--replace` (truncate + reload).

Direct local command (requires local `go>=1.25` and `sqlite3`):

```bash
cd backend
go run ./cmd/import_legacy \
  --stock /path/to/stock.xlsx \
  --sqlite /path/to/invoices.db \
  --sell-price /path/to/pro_clean_with_price.xlsx \
  --sell-price-threshold 96 \
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

## Docker deploy
Use the included multi-stage image (small runtime via `scratch`) and expose API on `1234`.

### Run with Docker Compose
```bash
cd backend
# optional overrides:
# export BACKEND_DATABASE_URL='postgres://USER:PASSWORD@host.docker.internal:5432/DB_NAME?sslmode=disable'
# export BACKEND_PORT=1234
docker compose up -d --build
```

Then access:
- local: `http://127.0.0.1:1234/healthz`
- server: `http://<SERVER_IP>:1234/healthz`

### PostgreSQL on host machine (localhost)
Inside containers, `localhost` points to the container itself.  
For host PostgreSQL, use `host.docker.internal` in `DATABASE_URL` (already set in `docker-compose.yml` for Linux with `host-gateway`):

`postgres://USER:PASSWORD@host.docker.internal:5432/DB_NAME?sslmode=disable`

`docker-compose.yml` reads these optional override vars:
- `BACKEND_DATABASE_URL`
- `BACKEND_PORT`

### Alternative: true host networking (Linux)
If you must keep `127.0.0.1` in `DATABASE_URL`, run with host network:
```bash
cd backend
docker build -t reza-backend:latest .
docker run -d --name reza-backend \
  --restart unless-stopped \
  --network host \
  -e PORT=1234 \
  -e DATABASE_URL='postgres://USER:PASSWORD@127.0.0.1:5432/DB_NAME?sslmode=disable' \
  reza-backend:latest
```
