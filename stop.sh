#!/bin/sh

# Kill uvicorn/FastAPI process
pkill -f "uvicorn main:app"

# Stop nginx gracefully
nginx -s quit

echo "Stopped FastAPI and Nginx servers"
