#!/bin/bash

# Function to cleanup child processes
cleanup() {
    echo "Received shutdown signal - cleaning up..."
    kill -TERM "$FASTAPI_PID" 2>/dev/null
    kill -TERM "$NGINX_PID" 2>/dev/null
    exit 0
}

# Setup signal handling
trap cleanup SIGTERM SIGINT SIGQUIT

# Start FastAPI
echo "Starting FastAPI..."
. /app/venv/bin/activate
uvicorn backend.main:app --host 0.0.0.0 --port 8000 --workers 4 --log-level debug \
    --log-config /app/logging.conf &
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
