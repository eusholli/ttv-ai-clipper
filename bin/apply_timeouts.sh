#!/bin/bash

# Change to the project root directory
cd "$(dirname "$0")/.."

# Load environment variables
if [ -f ".env" ]; then
    source .env
fi

# Check if required environment variables are set
if [ -z "$DB_NAME" ] || [ -z "$DB_USER" ] || [ -z "$DB_PWD" ] || [ -z "$DB_HOST" ]; then
    echo "Error: Required database environment variables are not set"
    exit 1
fi

# Apply the statement timeouts migration
PGPASSWORD=$DB_PWD psql -h $DB_HOST -U $DB_USER -d $DB_NAME -f backend/migrations/008_add_statement_timeouts.sql

echo "Database timeouts configuration applied successfully"
