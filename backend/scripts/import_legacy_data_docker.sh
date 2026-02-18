#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKEND_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
REPO_ROOT="$(cd "${BACKEND_DIR}/.." && pwd)"

DEFAULT_STOCK="${REPO_ROOT}/stock.xlsx"
DEFAULT_SQLITE="${REPO_ROOT}/invoices.db"
DEFAULT_SELL_PRICE="${REPO_ROOT}/pro_clean_with_price.xlsx"

IMAGE="${IMPORT_LEGACY_IMAGE:-reza-legacy-import:go1.25.7}"
NETWORK_MODE="${IMPORT_DOCKER_NETWORK_MODE:-host}"

if ! command -v docker >/dev/null 2>&1; then
  echo "error: docker command is required" >&2
  exit 1
fi

docker build -t "${IMAGE}" -f "${BACKEND_DIR}/Dockerfile.import_legacy" "${BACKEND_DIR}"

EXTRA_ARGS=("$@")
if [[ -f "${DEFAULT_SELL_PRICE}" ]]; then
  EXTRA_ARGS=(--sell-price "/work/pro_clean_with_price.xlsx" "${EXTRA_ARGS[@]}")
fi

DOCKER_RUN_ARGS=(
  run
  --rm
  -v "${REPO_ROOT}:/work"
  -w /work/backend
)
if [[ -n "${NETWORK_MODE}" ]]; then
  DOCKER_RUN_ARGS+=(--network "${NETWORK_MODE}")
fi
DOCKER_RUN_ARGS+=(
  "${IMAGE}"
  --stock "/work/stock.xlsx"
  --sqlite "/work/invoices.db"
  --replace
  "${EXTRA_ARGS[@]}"
)

docker "${DOCKER_RUN_ARGS[@]}"
