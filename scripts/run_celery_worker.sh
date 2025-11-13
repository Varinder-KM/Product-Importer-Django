#!/usr/bin/env bash

set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

if [ -d "${PROJECT_ROOT}/.venv" ]; then
  # shellcheck source=/dev/null
  source "${PROJECT_ROOT}/.venv/bin/activate"
fi

exec celery -A config worker --loglevel=info

