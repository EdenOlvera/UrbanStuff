#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
python -m venv .venv
.venv/bin/python -m pip install --cache-dir /tmp/umep-pip-cache -r requirements.lock.txt
npm --prefix frontend ci --cache /tmp/umep-npm-cache --no-audit --no-fund
npm --prefix frontend run build
