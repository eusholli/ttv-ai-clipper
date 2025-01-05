#!/usr/bin/env bash

REPO_ROOT="$(git rev-parse --show-toplevel)"
cd "$REPO_ROOT"

# Kill uvicorn/FastAPI process
pkill -f "uvicorn main:app"

# Stop nginx gracefully
nginx -s quit

echo "Stopped FastAPI and Nginx servers"
