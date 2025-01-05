#!/usr/bin/env bash

REPO_ROOT="$(git rev-parse --show-toplevel)"
cd "$REPO_ROOT"

# Function to cleanup child processes
cleanup() {
    echo "Received shutdown signal - cleaning up..."
    kill -TERM "$NGINX_PID" 2>/dev/null
    exit 0
}

# Setup signal handling
trap cleanup SIGTERM SIGINT SIGQUIT

# Only start frontend, use remote backend

# Start Nginx with logs to stderr
echo "Starting Nginx..."
nginx -g "daemon off; error_log stderr;" &
NGINX_PID=$!

# Wait for any process to exit
wait -n

# Exit with error if any process dies
exit 1
