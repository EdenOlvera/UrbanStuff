#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
mkdir -p .data/logs
children=()
cleanup() { trap - EXIT INT TERM; if ((${#children[@]})); then for child in "${children[@]}"; do kill -- "-$child" 2>/dev/null || true; done; wait "${children[@]}" 2>/dev/null || true; fi; }
trap cleanup EXIT INT TERM
setsid .venv/bin/python -m uvicorn backend.api:app --host 127.0.0.1 --port 8000 > .data/logs/api.log 2>&1 &
children+=("$!")
setsid .venv/bin/python -m backend.worker > .data/logs/worker.log 2>&1 &
children+=("$!")
setsid npm --prefix frontend run dev -- --port 5173 --strictPort > .data/logs/frontend.log 2>&1 &
children+=("$!")
for attempt in {1..50}; do
  if curl --fail --silent http://127.0.0.1:8000/api/health >/dev/null && curl --fail --silent http://127.0.0.1:5173 >/dev/null; then
    echo 'UMEP Studio API, worker, and frontend started. Logs: .data/logs/'
    wait -n "${children[@]}"
    exit 1
  fi
  for child in "${children[@]}"; do if ! kill -0 "$child" 2>/dev/null; then echo 'Startup failed. Inspect .data/logs/'; exit 1; fi; done
  sleep .2
done
echo 'Startup timed out. Inspect .data/logs/'
exit 1
