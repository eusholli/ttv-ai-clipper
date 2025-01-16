#!/bin/bash

# Exit on error
set -e

# Check if both service specifications are provided
if [ -z "$1" ] || [ -z "$2" ]; then
    echo "Error: Both service specifications are required"
    echo "Usage: $0 <project1-id>:<service-name-1> <project2-id>:<service-name-2>"
    echo "Example: $0 ttv-ai-clipper:ttv-ai-clipper staging-ai-clipper:staging-ai-clipper"
    exit 1
fi

# Parse service specifications
IFS=':' read -r PROJECT1 SERVICE1 <<< "$1"
IFS=':' read -r PROJECT2 SERVICE2 <<< "$2"

# Validate service specifications
if [ -z "$PROJECT1" ] || [ -z "$SERVICE1" ] || [ -z "$PROJECT2" ] || [ -z "$SERVICE2" ]; then
    echo "Error: Invalid service specification format"
    echo "Usage: $0 <project1-id>:<service-name-1> <project2-id>:<service-name-2>"
    echo "Example: $0 ttv-ai-clipper:ttv-ai-clipper staging-ai-clipper:staging-ai-clipper"
    exit 1
fi

REGION="us-central1"
REPORT_FILE="cloud-run-audit-$(date +%Y%m%d_%H%M%S).txt"
TEMP_DIR=$(mktemp -d)
trap 'rm -rf "$TEMP_DIR"' EXIT

# Function to check if gcloud is authenticated for a project
check_auth() {
    local project="$1"
    echo "Checking authentication for project: $project"
    if ! gcloud config set project "$project" &>/dev/null; then
        echo "Error: Not authenticated for project $project"
        exit 1
    fi
}

# Function to print section headers
print_header() {
    echo -e "\n=== $1 ===" | tee -a "$REPORT_FILE"
}

# Function to fetch service configuration
fetch_service_config() {
    local project="$1"
    local service="$2"
    local output_file="$3"
    
    echo "Fetching configuration for $service in project $project..."
    if ! gcloud run services describe "$service" \
        --project="$project" \
        --region="$REGION" \
        --format=json > "$output_file" 2>/dev/null; then
        echo "Error: Failed to fetch configuration for $service in project $project"
        exit 1
    fi
}

# Initialize report file
{
    echo "Cloud Run Service Comparison Report"
    echo "Generated on: $(date)"
    echo "Comparing $PROJECT1:$SERVICE1 with $PROJECT2:$SERVICE2"
    echo "Region: $REGION"
} > "$REPORT_FILE"

# Check authentication for both projects
check_auth "$PROJECT1"
check_auth "$PROJECT2"

# Fetch configurations
CONFIG1="$TEMP_DIR/${SERVICE1}_config.json"
CONFIG2="$TEMP_DIR/${SERVICE2}_config.json"
fetch_service_config "$PROJECT1" "$SERVICE1" "$CONFIG1"
fetch_service_config "$PROJECT2" "$SERVICE2" "$CONFIG2"

# Compare basic service configurations
print_header "Basic Configuration"
{
    echo -e "\n$PROJECT1:$SERVICE1 Configuration:"
    jq -r '.spec.template.spec.containers[0] | {
        image,
        resources: .resources.limits,
        concurrency: .concurrency,
        maxInstances: .maxInstances,
        minInstances: .minInstances
    }' "$CONFIG1"
    
    echo -e "\n$PROJECT2:$SERVICE2 Configuration:"
    jq -r '.spec.template.spec.containers[0] | {
        image,
        resources: .resources.limits,
        concurrency: .concurrency,
        maxInstances: .maxInstances,
        minInstances: .minInstances
    }' "$CONFIG2"
} >> "$REPORT_FILE"

# Compare environment variables
print_header "Environment Variables"
{
    echo "=== $PROJECT1:$SERVICE1 Environment Variables ==="
    jq -r '.spec.template.spec.containers[0].env[] | select(.valueFrom == null) | "\(.name)=\(.value)"' "$CONFIG1" || echo "No environment variables found"
    
    echo -e "\n=== $PROJECT2:$SERVICE2 Environment Variables ==="
    jq -r '.spec.template.spec.containers[0].env[] | select(.valueFrom == null) | "\(.name)=\(.value)"' "$CONFIG2" || echo "No environment variables found"
} >> "$REPORT_FILE"

# Compare secrets and their values
print_header "Secrets Comparison"
{
    echo "Fetching and comparing secrets..."
    
    # Get secrets from both services
    SECRETS1=$(jq -r '.spec.template.spec.containers[0].env[] | select(.valueFrom.secretKeyRef != null) | .valueFrom.secretKeyRef.name' "$CONFIG1" || echo "")
    SECRETS2=$(jq -r '.spec.template.spec.containers[0].env[] | select(.valueFrom.secretKeyRef != null) | .valueFrom.secretKeyRef.name' "$CONFIG2" || echo "")
    
    # Combine unique secret names
    ALL_SECRETS=$(echo -e "${SECRETS1}\n${SECRETS2}" | sort -u | grep -v '^$')
    
    if [ -z "$ALL_SECRETS" ]; then
        echo "No secrets found in either service"
    else
        echo -e "\n=== Detailed Secrets Comparison ==="
        while IFS= read -r SECRET_NAME; do
            echo -e "\nComparing secret: $SECRET_NAME"
            
            # Get secret values using latest version
            VALUE1=""
            VALUE2=""
            
            if echo "$SECRETS1" | grep -q "^${SECRET_NAME}$"; then
                VALUE1=$(gcloud secrets versions access latest \
                    --project="$PROJECT1" \
                    --secret="$SECRET_NAME" 2>/dev/null || echo "ERROR: Could not access secret")
            else
                echo "Secret $SECRET_NAME not found in $PROJECT1"
            fi
            
            if echo "$SECRETS2" | grep -q "^${SECRET_NAME}$"; then
                VALUE2=$(gcloud secrets versions access latest \
                    --project="$PROJECT2" \
                    --secret="$SECRET_NAME" 2>/dev/null || echo "ERROR: Could not access secret")
            else
                echo "Secret $SECRET_NAME not found in $PROJECT2"
            fi
            
            # Compare values if both exist
            if [ -n "$VALUE1" ] && [ -n "$VALUE2" ]; then
                if [ "$VALUE1" = "$VALUE2" ]; then
                    echo "✓ Values match"
                else
                    echo "⨯ Values differ"
                fi
            fi
        done <<< "$ALL_SECRETS"
    fi
} >> "$REPORT_FILE"

# Compare Cloud SQL connections
print_header "Cloud SQL Connections"
{
    echo "=== $PROJECT1:$SERVICE1 Cloud SQL ==="
    jq -r '.spec.template.spec.containers[0].cloudSqlInstances // "None"' "$CONFIG1"
    
    echo -e "\n=== $PROJECT2:$SERVICE2 Cloud SQL ==="
    jq -r '.spec.template.spec.containers[0].cloudSqlInstances // "None"' "$CONFIG2"
} >> "$REPORT_FILE"

# Compare IAM policies
print_header "IAM Policies"
{
    echo "=== $PROJECT1:$SERVICE1 IAM Policy ==="
    gcloud run services get-iam-policy "$SERVICE1" \
        --project="$PROJECT1" \
        --region="$REGION" \
        --format=json > "$TEMP_DIR/${SERVICE1}_iam.json"
    cat "$TEMP_DIR/${SERVICE1}_iam.json"
    
    echo -e "\n=== $PROJECT2:$SERVICE2 IAM Policy ==="
    gcloud run services get-iam-policy "$SERVICE2" \
        --project="$PROJECT2" \
        --region="$REGION" \
        --format=json > "$TEMP_DIR/${SERVICE2}_iam.json"
    cat "$TEMP_DIR/${SERVICE2}_iam.json"
} >> "$REPORT_FILE"

# Compare VPC connector settings
print_header "VPC Connector Settings"
{
    echo "$PROJECT1:$SERVICE1 VPC Connector:"
    jq -r '.spec.template.spec.vpcAccess.connector // "None"' "$CONFIG1"
    
    echo -e "\n$PROJECT2:$SERVICE2 VPC Connector:"
    jq -r '.spec.template.spec.vpcAccess.connector // "None"' "$CONFIG2"
} >> "$REPORT_FILE"

# Generate differences summary
print_header "Key Differences Summary"

# Compare container images
{
    IMAGE1=$(jq -r '.spec.template.spec.containers[0].image' "$CONFIG1")
    IMAGE2=$(jq -r '.spec.template.spec.containers[0].image' "$CONFIG2")
    if [ "$IMAGE1" != "$IMAGE2" ]; then
        echo "Container images differ:"
        echo "  $PROJECT1:$SERVICE1: $IMAGE1"
        echo "  $PROJECT2:$SERVICE2: $IMAGE2"
    fi

    # Compare IAM policies using diff
    echo -e "\nIAM Policy differences:"
    diff -u "$TEMP_DIR/${SERVICE1}_iam.json" "$TEMP_DIR/${SERVICE2}_iam.json" || true
} >> "$REPORT_FILE"

echo -e "\nAudit report generated: $REPORT_FILE"
echo "Review $REPORT_FILE for detailed comparison"
