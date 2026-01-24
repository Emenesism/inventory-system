# Reza Inventory Suite

A modern desktop accounting + inventory management UI built with PySide6.

## Features
- Sidebar navigation with dashboard-style layout
- Inventory view with search, sorting, and inline quantity edits
- Sales Excel/CSV import with preview, validation, and safe backups
- Purchase invoice entry with weighted average cost updates
- Fuzzy product autocomplete for purchase lines
- Toast notifications and light/dark theme toggle
- Logs stored at `logs/app.log`

## Requirements
- Python 3.10+

## Setup (Windows-friendly)
```bash
python -m venv .venv
.\.venv\Scripts\activate
pip install -r requirements.txt
python -m app.main
```

## Inventory File Format
Supported: `.xlsx`, `.xlsm`, `.csv`

Required columns:
- `product_name`
- `quantity`
- `avg_buy_price`

Optional columns (kept as-is):
- `sku` or `product_code`
- `last_updated`

## Notes
- On first launch, select the inventory file. The chosen path is saved in `config.json`.
- Before any updates, the app creates a timestamped backup next to the inventory file.
