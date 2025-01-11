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

# Function to cleanup child processes
cleanup() {
    echo "Received shutdown signal - cleaning up..."
    kill -TERM "$NGINX_PID" 2>/dev/null
    exit 0
}

# Setup signal handling
trap cleanup SIGTERM SIGINT SIGQUIT

# Start FastAPI
echo "Starting FastAPI..."
. /app/venv/bin/activate

APP_MODULE="backend.main:app"
HOST="0.0.0.0"
PORT="8000"

# Check if debug mode is enabled
if [ "$DEBUGPY_ENABLE" = "1" ]; then
    echo "Starting in debug mode with debugpy..."
    python -m debugpy \
        --listen $HOST:5678 \
        --wait-for-client \
        -m uvicorn $APP_MODULE \
        --host $HOST \
        --port $PORT \
        --workers 1 \
        --log-level debug &
else
    echo "Starting in production mode..."
    uvicorn $APP_MODULE \
        --host $HOST \
        --port $PORT \
        --workers 4 \
        --log-level info &
fi
FASTAPI_PID=$!

# Wait for FastAPI to start
echo "Waiting for FastAPI to start..."
while ! curl -s http://localhost:8000/api/health > /dev/null; do
    if ! kill -0 "$FASTAPI_PID" 2>/dev/null; then
        echo "FastAPI failed to start"
        exit 1
    fi
    sleep 1
done
echo "FastAPI is ready!"

# Start Nginx with logs to stderr
echo "Starting Nginx..."
nginx -g "daemon off; error_log stderr;" &
NGINX_PID=$!

# Wait for any process to exit
wait -n

# Exit with error if any process dies
exit 1
