#!/bin/bash
cd "$(dirname "$0")"
if [ -d "venv" ]; then
    source venv/bin/activate
elif [ -d ".venv" ]; then
    source .venv/bin/activate
fi
uvicorn app.main:app --host 0.0.0.0 --port 8009
