#!/usr/bin/env bash
set -e

echo "▶  Starting FastAPI backend..."
uvicorn backend.server:app --host 0.0.0.0 --port 8000 --reload &
BACKEND_PID=$!

sleep 2   # wait for backend to initialize DB

echo "▶  Starting Streamlit frontend..."
streamlit run frontend/app.py --server.port 8501 &
FRONTEND_PID=$!

echo ""
echo "✅  System running:"
echo "   API docs  →  http://localhost:8000/docs"
echo "   Dashboard →  http://localhost:8501"
echo ""
echo "Press Ctrl+C to stop."

trap "kill $BACKEND_PID $FRONTEND_PID" INT TERM
wait
