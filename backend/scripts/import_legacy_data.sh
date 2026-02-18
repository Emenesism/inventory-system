#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKEND_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"

DEFAULT_STOCK="${BACKEND_DIR}/../stock.xlsx"
DEFAULT_SQLITE="${BACKEND_DIR}/../invoices.db"
DEFAULT_SELL_PRICE="${BACKEND_DIR}/../pro_clean_with_price.xlsx"

cd "${BACKEND_DIR}"

EXTRA_ARGS=("$@")
if [[ -f "${DEFAULT_SELL_PRICE}" ]]; then
  EXTRA_ARGS=(--sell-price "${DEFAULT_SELL_PRICE}" "${EXTRA_ARGS[@]}")
fi

go run ./cmd/import_legacy \
  --stock "${DEFAULT_STOCK}" \
  --sqlite "${DEFAULT_SQLITE}" \
  --replace \
  "${EXTRA_ARGS[@]}"
