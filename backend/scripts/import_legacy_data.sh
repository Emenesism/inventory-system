#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKEND_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"

DEFAULT_STOCK="${BACKEND_DIR}/../stock.xlsx"
DEFAULT_SQLITE="${BACKEND_DIR}/../invoices.db"
DEFAULT_SELL_PRICE="${BACKEND_DIR}/../pro_clean_with_price.xlsx"

go_is_supported() {
  local raw major minor
  raw="$(go env GOVERSION 2>/dev/null || true)"
  if [[ -z "${raw}" ]]; then
    raw="$(go version 2>/dev/null | awk '{print $3}')"
  fi
  raw="${raw#go}"
  major="${raw%%.*}"
  raw="${raw#*.}"
  minor="${raw%%[^0-9]*}"
  if [[ -z "${major}" || -z "${minor}" ]]; then
    return 1
  fi
  if (( major > 1 )); then
    return 0
  fi
  (( minor >= 25 ))
}

if ! command -v go >/dev/null 2>&1 || ! command -v sqlite3 >/dev/null 2>&1 || ! go_is_supported; then
  if command -v docker >/dev/null 2>&1; then
    echo "info: go>=1.25 and sqlite3 not available locally; using Docker importer" >&2
    exec "${SCRIPT_DIR}/import_legacy_data_docker.sh" "$@"
  fi
  echo "error: legacy import needs go >= 1.25 and sqlite3, or docker for fallback" >&2
  exit 1
fi

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
