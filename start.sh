#!/bin/bash -x

# Setup proper process management
setup_signals() {
    trap 'kill $(jobs -p)' SIGTERM SIGINT
}
setup_signals

python backend/test_postgresql.py

# Start FastAPI
echo "Starting FastAPI..."
. /app/venv/bin/activate
uvicorn backend.main:app --host 0.0.0.0 --port 8000 --workers 4 --log-level debug \
    --log-config /app/logging.conf &
# Store the PID
UVICORN_PID=$!

# Wait for FastAPI to be ready
echo "Waiting for FastAPI to start..."
for i in {1..30}; do
    if curl -s http://localhost:8000/api/health >/dev/null; then
        echo "FastAPI is ready!"
        break
    fi
    if [ $i -eq 30 ]; then
        echo "FastAPI failed to start"
        exit 1
    fi
    sleep 1
done

# Start Nginx only after FastAPI is confirmed running
echo "Starting Nginx..."
nginx -g "daemon off;" &
NGINX_PID=$!

# Monitor both processes
while kill -0 $UVICORN_PID && kill -0 $NGINX_PID 2>/dev/null; do
    sleep 1
done

# If we get here, one of the processes died
if ! kill -0 $UVICORN_PID 2>/dev/null; then
    echo "FastAPI died"
    exit 1
fi
if ! kill -0 $NGINX_PID 2>/dev/null; then
    echo "Nginx died"
    exit 1
fi
