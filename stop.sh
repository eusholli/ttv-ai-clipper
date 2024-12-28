#!/bin/sh

# Kill uvicorn/FastAPI process
pkill -f "uvicorn main:app"

# Stop nginx gracefully
nginx -s quit

# Stop PostgreSQL gracefully
pg_ctlcluster 16 main stop

echo "Stopped FastAPI, Nginx, and PostgreSQL servers"
