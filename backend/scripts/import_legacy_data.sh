#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKEND_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"

DEFAULT_STOCK="${BACKEND_DIR}/../stock.xlsx"
DEFAULT_SQLITE="${BACKEND_DIR}/../invoices.db"

cd "${BACKEND_DIR}"

go run ./cmd/import_legacy \
  --stock "${DEFAULT_STOCK}" \
  --sqlite "${DEFAULT_SQLITE}" \
  --replace \
  "$@"
