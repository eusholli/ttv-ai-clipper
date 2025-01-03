#!/bin/bash -x

# Setup proper process management
setup_signals() {
    trap 'kill $(jobs -p)' SIGTERM SIGINT
}
setup_signals

# Start FastAPI
echo "Starting FastAPI..."
. /app/venv/bin/activate
uvicorn backend.main:app --host 0.0.0.0 --port 8000 --workers 4 --log-level debug \
    --log-config /app/logging.conf &
# Store the PID
UVICORN_PID=$!

# Start Nginx
echo "Starting Nginx..."
nginx -g "daemon off;" &
NGINX_PID=$!

# Wait for any process to exit
wait -n

# Exit with status of process that exited first
exit $?
