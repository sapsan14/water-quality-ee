#!/usr/bin/env bash
# Пересборка citizen snapshot: координаты и уезд — только OpenCage (OPENCAGE_API_KEY).
# Из корня репозитория (см. citizen-service/GEO_SECRETS.md).
#
# Примеры:
#   ./scripts/refresh_citizen_geo.sh --map-only
#   GEOCODE_HTTP_LIMIT=12000 ./scripts/refresh_citizen_geo.sh
#   ./scripts/refresh_citizen_geo.sh   # полный прогон + 4 модели (дольше)
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

if [ -f "$ROOT/.env" ]; then
  set -a
  # shellcheck disable=SC1091
  . "$ROOT/.env"
  set +a
fi

LIMIT="${GEOCODE_HTTP_LIMIT:-8000}"
export OPENCAGE_API_KEY="${OPENCAGE_API_KEY:-}"

exec python citizen-service/scripts/build_citizen_snapshot.py \
  --infer-county \
  --resolve-coordinates \
  --geocode-limit "$LIMIT" \
  "$@"
