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

echo "Starting secret migration from $SOURCE_PROJECT to $DEST_PROJECT for service $SERVICE_NAME"

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

# Get service account email for the Cloud Run service in destination project
SERVICE_ACCOUNT=$(gcloud run services describe "$SERVICE_NAME" \
    --project "$DEST_PROJECT" \
    --format="get(spec.template.spec.serviceAccountName)" \
    2>/dev/null || echo "")

if [ -z "$SERVICE_ACCOUNT" ]; then
    echo "Service account not found in Cloud Run service, getting project number to use default compute service account..."
    PROJECT_NUMBER=$(gcloud projects describe "$DEST_PROJECT" --format="get(projectNumber)")
    SERVICE_ACCOUNT="${PROJECT_NUMBER}-compute@developer.gserviceaccount.com"
    echo "Using default compute service account: $SERVICE_ACCOUNT"
fi

# Get list of secrets from source project
echo "Retrieving secrets from source project..."
SECRETS=$(gcloud secrets list --project="$SOURCE_PROJECT" \
    --format="value(name.basename())" 2>/dev/null || echo "")

if [ -z "$SECRETS" ]; then
    echo "No secrets found in source project"
    exit 0
fi

# Process each secret
for SECRET_NAME in $SECRETS; do
    echo "Processing secret: $SECRET_NAME"
    
    # Get latest version of the secret from source project
    SECRET_VALUE=$(gcloud secrets versions access latest \
        --secret="$SECRET_NAME" \
        --project="$SOURCE_PROJECT" 2>/dev/null)
    
    if [ -z "$SECRET_VALUE" ]; then
        echo "Warning: Could not access value for secret $SECRET_NAME, skipping..."
        continue
    fi
    
    # Check if secret exists in destination project
    if gcloud secrets describe "$SECRET_NAME" \
        --project="$DEST_PROJECT" &>/dev/null; then
        echo "Secret $SECRET_NAME already exists in destination project, updating..."
        echo "$SECRET_VALUE" | gcloud secrets versions add "$SECRET_NAME" \
            --project="$DEST_PROJECT" \
            --data-file=- 2>/dev/null
    else
        echo "Creating new secret $SECRET_NAME in destination project..."
        echo "$SECRET_VALUE" | gcloud secrets create "$SECRET_NAME" \
            --project="$DEST_PROJECT" \
            --data-file=- 2>/dev/null
    fi
    
    # Grant access to the service account
    gcloud secrets add-iam-policy-binding "$SECRET_NAME" \
        --project="$DEST_PROJECT" \
        --member="serviceAccount:$SERVICE_ACCOUNT" \
        --role="roles/secretmanager.secretAccessor" 2>/dev/null
    
    echo "Successfully processed secret: $SECRET_NAME"
done

# Update Cloud Run service to use the secrets
echo "Updating Cloud Run service to use secrets..."

# Build the secrets flag string
SECRETS_FLAGS=""
for SECRET_NAME in $SECRETS; do
    SECRETS_FLAGS="$SECRETS_FLAGS --set-secrets=$SECRET_NAME=$SECRET_NAME:latest"
done

# Update the Cloud Run service
gcloud run services update "$SERVICE_NAME" \
    --project="$DEST_PROJECT" \
    $SECRETS_FLAGS

echo "Secret migration completed successfully!"
