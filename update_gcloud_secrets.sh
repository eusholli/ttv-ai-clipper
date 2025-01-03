#!/bin/bash

# Check if gcloud is installed
if ! command -v gcloud &> /dev/null; then
    echo "Error: gcloud CLI is not installed. Please install it first."
    exit 1
fi

# Check if user is authenticated
if ! gcloud auth list --filter=status:ACTIVE --format="value(account)" 2>/dev/null | grep -q "@"; then
    echo "Error: Not authenticated to Google Cloud. Please run 'gcloud auth login' first."
    exit 1
fi

# Prompt for project ID if not already set
CURRENT_PROJECT=$(gcloud config get-value project 2>/dev/null)
if [ -z "$CURRENT_PROJECT" ]; then
    echo "Error: No Google Cloud project is set. Please run 'gcloud config set project YOUR_PROJECT_ID' first."
    exit 1
fi

echo "Using Google Cloud project: $CURRENT_PROJECT"
echo "Starting secrets update process..."

while IFS= read -r line; do
    # Skip empty lines and comments
    [[ -z "$line" || "$line" =~ ^[[:space:]]*# ]] && continue
    
    # Get key and value
    key=$(echo "$line" | cut -d '=' -f 1)
    value=$(echo "$line" | cut -d '=' -f 2-)
    
    # Skip if key is empty
    [ -z "$key" ] && continue
    
    echo "Processing secret $key"
    
    # Check if secret exists
    if gcloud secrets describe "$key" &>/dev/null; then
        echo "Secret $key exists, updating value..."
        echo -n "$value" | gcloud secrets versions add "$key" --data-file=- || {
            echo "Error: Failed to update secret $key"
            exit 1
        }
    else
        echo "Creating new secret $key"
        gcloud secrets create "$key" --replication-policy="automatic" || {
            echo "Error: Failed to create secret $key"
            exit 1
        }
        echo "Adding initial version for secret $key"
        echo -n "$value" | gcloud secrets versions add "$key" --data-file=- || {
            echo "Error: Failed to add initial version for secret $key"
            exit 1
        }
    fi
    
    echo "Successfully processed secret $key"
done < .env
