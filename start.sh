#!/bin/bash -x

# Setup signal handling
trap 'kill $(jobs -p)' EXIT

# Start FastAPI
echo "Starting FastAPI..."
. /app/venv/bin/activate
uvicorn backend.main:app --host 0.0.0.0 --port 8000 --workers 4 --log-level debug \
    --log-config /app/logging.conf &

# Wait for FastAPI to be ready
echo "Waiting for FastAPI to be ready..."
timeout 30 bash -c 'until curl -s http://localhost:8000/api/filters > /dev/null 2>&1; do sleep 1; done' || {
    echo "FastAPI failed to start within 30 seconds"
    exit 1
}
echo "FastAPI is ready"

# Start Nginx
echo "Starting Nginx..."
nginx -g "daemon off;" 2>/var/log/nginx/error.log
