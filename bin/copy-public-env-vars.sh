#!/bin/bash

# Exit on error
set -e

# Check if source project ID is provided
if [ -z "$1" ]; then
    echo "Error: Source project ID not provided"
    echo "Usage: $0 <source-project-id> <destination-project-id> <destination-service-name>"
    echo "Example: $0 ttv-ai-clipper staging-ai-clipper staging-ai-clipper"
    echo "Note: destination-service-name is the Cloud Run service name in the destination project"
    exit 1
fi

# Check if destination project ID is provided
if [ -z "$2" ]; then
    echo "Error: Destination project ID not provided"
    echo "Usage: $0 <source-project-id> <destination-project-id> <destination-service-name>"
    echo "Example: $0 ttv-ai-clipper staging-ai-clipper staging-ai-clipper"
    echo "Note: destination-service-name is the Cloud Run service name in the destination project"
    exit 1
fi

# Check if service name is provided
if [ -z "$3" ]; then
    echo "Error: Destination service name not provided"
    echo "Usage: $0 <source-project-id> <destination-project-id> <destination-service-name>"
    echo "Example: $0 ttv-ai-clipper staging-ai-clipper staging-ai-clipper"
    echo "Note: destination-service-name is the Cloud Run service name in the destination project"
    exit 1
fi

SOURCE_PROJECT="$1"
DEST_PROJECT="$2"
SERVICE_NAME="$3"

echo "Starting environment variable migration from $SOURCE_PROJECT to $DEST_PROJECT for service $SERVICE_NAME"

# Function to check if gcloud is authenticated for a project
check_auth() {
    local project="$1"
    echo "Executing: gcloud config set project $project"
    if ! gcloud config set project "$project" &>/dev/null; then
        echo "Error: Not authenticated for project $project"
        exit 1
    fi
}

# Check authentication for both projects
check_auth "$SOURCE_PROJECT"
check_auth "$DEST_PROJECT"

# Get environment variables from source project
echo "Retrieving environment variables from source project..."
echo "Executing: gcloud run services describe $SERVICE_NAME --project=$SOURCE_PROJECT --format=json"
SERVICE_CONFIG=$(gcloud run services describe "$SERVICE_NAME" \
    --project="$SOURCE_PROJECT" \
    --format=json)

echo "Found environment variables in source project:"
echo "$SERVICE_CONFIG" | jq -r '.spec.template.spec.containers[0].env[] | "  \(.name): \(.value)"'

# Extract environment variables that are not secret references
ENV_VARS=$(echo "$SERVICE_CONFIG" | jq -r '.spec.template.spec.containers[0].env[] | select(.valueFrom == null) | "\(.name)=\(.value)"')

if [ -z "$ENV_VARS" ]; then
    echo "No public environment variables found in source project"
    exit 0
fi

echo -e "\nProcessing environment variables..."
echo "Variables to be updated:"
echo "$ENV_VARS" | while IFS= read -r line; do
    echo "  $line"
done

# Convert the environment variables into a format suitable for --update-env-vars
UPDATE_ENV_VARS=""
while IFS= read -r line; do
    if [ -n "$line" ]; then
        if [ -n "$UPDATE_ENV_VARS" ]; then
            UPDATE_ENV_VARS="$UPDATE_ENV_VARS,"
        fi
        UPDATE_ENV_VARS="$UPDATE_ENV_VARS$line"
    fi
done <<< "$ENV_VARS"

if [ -n "$UPDATE_ENV_VARS" ]; then
    echo "Updating environment variables in destination service..."
    echo "Executing: gcloud run services update $SERVICE_NAME --project=$DEST_PROJECT --update-env-vars=\"$UPDATE_ENV_VARS\""
    gcloud run services update "$SERVICE_NAME" \
        --project="$DEST_PROJECT" \
        --update-env-vars="$UPDATE_ENV_VARS"
    echo "Environment variables updated successfully!"
else
    echo "No public environment variables to update"
fi

echo "Environment variable migration completed successfully!"
