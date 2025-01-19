#!/usr/bin/env bash

# Check if both arguments are provided
if [ "$#" -ne 2 ]; then
    echo "Error: Two arguments required"
    echo "Usage: $0 <path/to/.env> <path/to/schema.sql>"
    exit 1
fi

ENV_FILE="$1"
SCHEMA_FILE="$2"

# Check if files exist
if [ ! -f "$ENV_FILE" ]; then
    echo "Error: .env file not found at $ENV_FILE"
    exit 1
fi

if [ ! -f "$SCHEMA_FILE" ]; then
    echo "Error: Schema file not found at $SCHEMA_FILE"
    exit 1
fi

# Load environment variables from .env file
export $(cat "$ENV_FILE" | grep -v '^#' | xargs)

# Check for required environment variables
required_vars=("DB_NAME" "DB_USER" "DB_PWD" "DB_HOST")
for var in "${required_vars[@]}"; do
    if [ -z "${!var}" ]; then
        echo "Error: Required environment variable $var is not set"
        exit 1
    fi
done

# Ask for confirmation
read -p "Are you sure you want to do this? Y/n: " confirm
if [[ "$confirm" != "Y" ]]; then
    echo "Operation aborted"
    exit 1
fi

# Run the schema file
PGPASSWORD=$DB_PWD psql -h $DB_HOST -U $DB_USER -d $DB_NAME -f "$SCHEMA_FILE"

# Check if the command was successful
if [ $? -eq 0 ]; then
    echo "Schema applied successfully"
else
    echo "Error applying schema"
    exit 1
fi
