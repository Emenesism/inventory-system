# Armkala Inventory Suite

A desktop accounting + inventory management app built with PySide6 for fast
daily operations. Branding and website: `armkala.ir`.

## Highlights
- Inventory management with search, sorting, and inline edits
- Sales import from Excel/CSV with preview and validation
- Purchase invoice entry with weighted average cost updates
- Analytics and low‑stock views with export
- Basalam orders fetch + export (filtered by status)
- Persistent settings and rotating logs

## Requirements
- Python 3.10+

## Quick start (Windows)
```bash
python -m venv .venv
.\.venv\Scripts\activate
pip install -r requirements.txt
python -m app.main
```

## Inventory file format
Supported: `.xlsx`, `.xlsm`, `.csv`

Required columns:
- `product_name`
- `quantity`
- `avg_buy_price`

Optional columns (kept as‑is):
- `sku` or `product_code`
- `last_updated`

## Configuration
Settings are stored in `config.json`:
- `inventory_file` (path)
- `theme` (`light` or `dark`)
- `low_stock_threshold` (int)
- `backup_dir` (path or null)
- `passcode` (string)
- `access_token` (Basalam API token)

## Basalam orders
The Basalam page:
- Uses vendor ID `563284` (hardcoded)
- Fetches all pages with `limit=30`
- Requests `tab=COMPLECTED` (Basalam’s enum spelling)
- Filters results to **وضعیت سفارش = رضایت مشتری**
- Shows/export only: Customer Name, Product Name, Quantity

## Logs
Logs are stored at `logs/app.log` and visible in the Reports/Logs page.

## Troubleshooting
- If Basalam fetch fails, check `access_token` in `config.json`.
- If inventory doesn’t load, verify required columns and file path.
