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

# Start Nginx with logs to stderr
echo "Starting Nginx..."
nginx -g "daemon off; error_log stderr;" &
NGINX_PID=$!

# Wait for any process to exit
wait -n

# Exit with error if any process dies
exit 1
