#!/usr/bin/env bash

# Configuration
EXISTING_SERVICE="ttv-ai-clipper"
NEW_SERVICE="staging-ai-clipper"
REGION="us-central1"
CONFIG_FILE="cloud-run-config.json"

# Error handling
set -e

echo "Starting Cloud Run configuration sync process..."

# Function to fetch and store configuration
fetch_and_store_config() {
    local SERVICE=$1
    echo "Fetching configuration for $SERVICE..."
    
    # Basic configuration
    gcloud run services describe $SERVICE \
        --region=$REGION \
        --format=json > temp_config.json

    # Extract specific fields into a new JSON structure
    jq '{
        image: (.spec.template.spec.containers[0].image // null),
        cpu: (.spec.template.spec.containers[0].resources.limits.cpu // null),
        memory: (.spec.template.spec.containers[0].resources.limits.memory // null),
        port: (.spec.template.spec.containers[0].ports[0].containerPort // null),
        concurrency: (.spec.template.spec.containers[0].containerConcurrency // null),
        maxInstances: (.spec.template.maxInstances // null),
        minInstances: (.spec.template.minInstances // null),
        env: (.spec.template.spec.containers[0].env // []),
        secrets: (try (.spec.template.spec.containers[0].envFrom[].secretRef.name) catch [] | if . then [.] else [] end),
        cloudSqlInstances: (.spec.template.spec.containers[0].cloudSqlInstances // []),
        vpcConnector: (.spec.template.spec.vpcAccess.connector // null)
    }' temp_config.json > "${SERVICE}_config.json"

    # Get IAM policy
    gcloud run services get-iam-policy $SERVICE \
        --region=$REGION \
        --format=json > "${SERVICE}_iam.json"

    # Combine configs into single JSON
    jq -s '{ 
        "'$SERVICE'": {
            "config": .[0],
            "iam": .[1]
        }
    }' "${SERVICE}_config.json" "${SERVICE}_iam.json" > "${SERVICE}_combined.json"

    # Cleanup temp files
    rm -f temp_config.json "${SERVICE}_config.json" "${SERVICE}_iam.json"

    echo "Configuration stored for $SERVICE"
}

# Check if config file exists
if [ -f "$CONFIG_FILE" ]; then
    echo "Found existing config file"
    cp "$CONFIG_FILE" "${CONFIG_FILE}.backup"
else
    echo "Creating new config file"
    echo "{}" > "$CONFIG_FILE"
fi

# Fetch configurations
fetch_and_store_config $EXISTING_SERVICE
fetch_and_store_config $NEW_SERVICE

# Merge configurations into main config file
jq -s '.[0] * .[1] * .[2]' "$CONFIG_FILE" "${EXISTING_SERVICE}_combined.json" "${NEW_SERVICE}_combined.json" > "${CONFIG_FILE}.new"
mv "${CONFIG_FILE}.new" "$CONFIG_FILE"

# Cleanup combined files
rm -f "${EXISTING_SERVICE}_combined.json" "${NEW_SERVICE}_combined.json"

echo "Comparing configurations..."

# Function to update service configuration
update_service_config() {
    echo "Updating $NEW_SERVICE configuration..."

    # Get existing service config
    EXISTING_CONFIG=$(jq -r ".\"$EXISTING_SERVICE\".config" "$CONFIG_FILE")
    
    # Update service with missing configurations
    gcloud run services update $NEW_SERVICE \
        --region=$REGION \
        --concurrency=$(echo "$EXISTING_CONFIG" | jq -r '.concurrency // "80"') \
        --max-instances=$(echo "$EXISTING_CONFIG" | jq -r '.maxInstances // "10"') \
        --min-instances=$(echo "$EXISTING_CONFIG" | jq -r '.minInstances // "0"')

    # Update VPC connector if exists
    VPC_CONNECTOR=$(echo "$EXISTING_CONFIG" | jq -r '.vpcConnector')
    if [ "$VPC_CONNECTOR" != "null" ] && [ ! -z "$VPC_CONNECTOR" ]; then
        echo "Setting VPC connector: $VPC_CONNECTOR"
        gcloud run services update $NEW_SERVICE \
            --region=$REGION \
            --vpc-connector=$VPC_CONNECTOR
    fi

    echo "Configuration updated successfully"
}

# Update staging service with any missing config
update_service_config

echo "Configuration sync completed!"
echo "Configuration stored in: $CONFIG_FILE"

# Print summary of configurations
echo -e "\nConfiguration Summary:"
echo "========================"
jq -r '
    . as $root |
    ["'$EXISTING_SERVICE'", "'$NEW_SERVICE'"] |
    .[] as $service |
    "\($service):",
    "  Image: \($root[$service].config.image)",
    "  CPU: \($root[$service].config.cpu)",
    "  Memory: \($root[$service].config.memory)",
    "  Concurrency: \($root[$service].config.concurrency)",
    "  Max Instances: \($root[$service].config.maxInstances)",
    "  Min Instances: \($root[$service].config.minInstances)",
    "  VPC Connector: \($root[$service].config.vpcConnector // "none")",
    "  Cloud SQL Instances: \($root[$service].config.cloudSqlInstances // "none")",
    "  Number of Secrets: \([$root[$service].config.secrets[]] | length)",
    ""
' "$CONFIG_FILE"
