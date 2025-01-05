#!/usr/bin/env bash

# Determine the root directory
if [ -d "/app" ]; then
    # Container environment
    ROOT_DIR="/app"
else
    # Local environment - try git first, fallback to script location
    if command -v git >/dev/null 2>&1 && git rev-parse --show-toplevel >/dev/null 2>&1; then
        ROOT_DIR="$(git rev-parse --show-toplevel)"
    else
        # Fallback to finding the script's location
        SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
        ROOT_DIR="$( cd "$SCRIPT_DIR/.." && pwd )"
    fi
fi

cd "$ROOT_DIR"

# Kill uvicorn/FastAPI process
pkill -f "uvicorn main:app"

# Stop nginx gracefully
nginx -s quit

echo "Stopped FastAPI and Nginx servers"
