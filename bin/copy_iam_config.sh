#!/bin/bash

# Exit on error
set -e

# Check if source project ID is provided
if [ -z "$1" ]; then
    echo "Error: Source project ID not provided"
    echo "Usage: $0 <source-project-id> <destination-project-id>"
    echo "Example: $0 ttv-ai-clipper staging-ai-clipper"
    exit 1
fi

# Check if destination project ID is provided
if [ -z "$2" ]; then
    echo "Error: Destination project ID not provided"
    echo "Usage: $0 <source-project-id> <destination-project-id>"
    echo "Example: $0 ttv-ai-clipper staging-ai-clipper"
    exit 1
fi

SOURCE_PROJECT="$1"
DEST_PROJECT="$2"

echo "Starting Default compute service account role migration from $SOURCE_PROJECT to $DEST_PROJECT"

# Function to check if gcloud is authenticated for a project
check_auth() {
    local project="$1"
    if ! gcloud config set project "$project" &>/dev/null; then
        echo "Error: Not authenticated for project $project"
        exit 1
    fi
}

# Check authentication for both projects
check_auth "$SOURCE_PROJECT"
check_auth "$DEST_PROJECT"

# Create temporary directory for IAM data
TEMP_DIR=$(mktemp -d)
trap 'rm -rf "$TEMP_DIR"' EXIT

# Get source project's Default compute service account
SOURCE_SA="$(gcloud projects describe $SOURCE_PROJECT --format='value(projectNumber)')"-compute@developer.gserviceaccount.com
DEST_SA="$(gcloud projects describe $DEST_PROJECT --format='value(projectNumber)')"-compute@developer.gserviceaccount.com

echo "Source Default compute service account: $SOURCE_SA"
echo "Destination Default compute service account: $DEST_SA"

# Get source project IAM policy
echo "Retrieving IAM policy from source project..."
if ! gcloud projects get-iam-policy "$SOURCE_PROJECT" --format=json > "$TEMP_DIR/source_policy.json"; then
    echo "Error: Failed to retrieve IAM policy from source project"
    exit 1
fi

# Process IAM bindings for Default compute service account
echo "Processing IAM bindings..."
jq -r --arg SA "serviceAccount:$SOURCE_SA" '.bindings[] | select(.members[] | contains($SA)) | .role' "$TEMP_DIR/source_policy.json" | while read -r ROLE; do
    echo "Processing role: $ROLE"
    
    # Add IAM binding to destination project's Default compute service account
    echo "Adding binding to destination project..."
    if ! gcloud projects add-iam-policy-binding "$DEST_PROJECT" \
        --member="serviceAccount:$DEST_SA" \
        --role="$ROLE" \
        --quiet 2>/dev/null; then
        echo "Warning: Failed to add binding for $DEST_SA with role $ROLE"
    fi
done

echo "Default compute service account role migration completed!"
echo "Please review the destination project's IAM configuration to ensure all necessary permissions are set correctly"
