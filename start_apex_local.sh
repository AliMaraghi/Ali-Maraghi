#!/usr/bin/env bash
# Runs the REAL existing backend (scripts/voice_api.py, waitress WSGI - not FastAPI; see that
# file's own docstring for why uvicorn is deliberately not used here) and the REAL existing
# frontend (apex-ui/, a vite dev server) entirely on localhost, with no dependency on
# ui.apexcorelab.uk or api.apexcorelab.uk reachability. This does NOT create a second,
# parallel backend - voice_api.py already has conversation memory (the real SQLite
# voice_turns/voice_embeddings tables inside runtime/kernel.sqlite3, confirmed by reading the
# file directly) and the real orchestrator.py routing - this script only runs that code
# locally instead of adding a new stack next to it.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKEND_PORT="${BACKEND_PORT:-8000}"
FRONTEND_PORT="${FRONTEND_PORT:-5173}"

cleanup() {
  [ -n "${BACKEND_PID:-}" ] && kill "$BACKEND_PID" 2>/dev/null || true
  [ -n "${FRONTEND_PID:-}" ] && kill "$FRONTEND_PID" 2>/dev/null || true
}
trap cleanup EXIT INT TERM

echo "[start_apex_local] Starting backend (scripts/voice_api.py) on http://127.0.0.1:${BACKEND_PORT} ..."
APEX_VOICE_ALLOWED_ORIGIN="http://localhost:${FRONTEND_PORT}" \
  PYTHONPATH="$ROOT/core:$ROOT/scripts" \
  python3 -B "$ROOT/scripts/voice_api.py" --port "$BACKEND_PORT" &
BACKEND_PID=$!
sleep 1

if ! kill -0 "$BACKEND_PID" 2>/dev/null; then
  echo "[start_apex_local] FATAL: backend process exited immediately - it did not stay up."
  echo "[start_apex_local] Run 'python3 -B scripts/voice_api.py --port ${BACKEND_PORT}' directly to see the real error."
  exit 1
fi

echo "[start_apex_local] Backend is up (pid $BACKEND_PID)."
echo "[start_apex_local] Starting frontend (apex-ui, vite dev server) on http://localhost:${FRONTEND_PORT} ..."
( cd "$ROOT/apex-ui" && VITE_CHAT_ENDPOINT="http://localhost:${BACKEND_PORT}/api/chat" \
    npm run dev -- --port "$FRONTEND_PORT" --strictPort ) &
FRONTEND_PID=$!
sleep 2

if ! kill -0 "$FRONTEND_PID" 2>/dev/null; then
  echo "[start_apex_local] FATAL: frontend process exited immediately."
  exit 1
fi

cat <<EOF

[start_apex_local] Both processes are running:
  Backend:   http://localhost:${BACKEND_PORT}/api/chat   (pid $BACKEND_PID)
  Frontend:  http://localhost:${FRONTEND_PORT}            (pid $FRONTEND_PID)

The frontend's CORS-allowed origin is set to http://localhost:${FRONTEND_PORT} for this
run only (APEX_VOICE_ALLOWED_ORIGIN) - the hosted https://ui.apexcorelab.uk default in
scripts/voice_api.py is unchanged by running this script.

The backend fails closed (HTTP 402) on any request that needs a real LLM call until a
daily spend cap is configured:
  python3 -B scripts/voice_api.py --set-daily-cap-pence <N>
Locally-handled queries (e.g. "system status") work with zero spend and zero cap needed.

Press Ctrl+C to stop both.
EOF

wait
