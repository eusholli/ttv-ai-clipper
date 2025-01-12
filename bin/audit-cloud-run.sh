#!/usr/bin/env bash

# Configuration
SERVICE1="ttv-ai-clipper"
SERVICE2="staging-ai-clipper"
REGION="us-central1"
REPORT_FILE="cloud-run-audit-$(date +%Y%m%d_%H%M%S).txt"

# Function to print section headers
print_header() {
    echo -e "\n=== $1 ===" | tee -a $REPORT_FILE
}

# Initialize report file
echo "Cloud Run Service Comparison Report" > $REPORT_FILE
echo "Generated on: $(date)" >> $REPORT_FILE
echo "Comparing $SERVICE1 with $SERVICE2" >> $REPORT_FILE
echo "Region: $REGION" >> $REPORT_FILE

# Compare basic service configurations
print_header "Basic Configuration"
for SERVICE in $SERVICE1 $SERVICE2; do
    echo -e "\n$SERVICE Configuration:" >> $REPORT_FILE
    gcloud run services describe $SERVICE \
        --region=$REGION \
        --format="table(
            spec.template.spec.containers[0].image,
            spec.template.spec.containers[0].resources.limits.cpu,
            spec.template.spec.containers[0].resources.limits.memory,
            spec.template.containers.concurrency,
            spec.template.containers.maxInstances,
            spec.template.containers.minInstances
        )" >> $REPORT_FILE
done

# Compare environment variables
print_header "Environment Variables"
echo "=== $SERVICE1 Environment Variables ===" >> $REPORT_FILE
gcloud run services describe $SERVICE1 --region=$REGION \
    --format="value(spec.template.spec.containers[0].env)" | tr ';' '\n' >> $REPORT_FILE

echo -e "\n=== $SERVICE2 Environment Variables ===" >> $REPORT_FILE
gcloud run services describe $SERVICE2 --region=$REGION \
    --format="value(spec.template.spec.containers[0].env)" | tr ';' '\n' >> $REPORT_FILE

# Compare secret references
print_header "Secret References"
echo "=== $SERVICE1 Secrets ===" >> $REPORT_FILE
gcloud run services describe $SERVICE1 --region=$REGION \
    --format="value(spec.template.spec.containers[0].envFrom[].secretRef.name)" >> $REPORT_FILE

echo -e "\n=== $SERVICE2 Secrets ===" >> $REPORT_FILE
gcloud run services describe $SERVICE2 --region=$REGION \
    --format="value(spec.template.spec.containers[0].envFrom[].secretRef.name)" >> $REPORT_FILE

# Compare Cloud SQL connections
print_header "Cloud SQL Connections"
echo "=== $SERVICE1 Cloud SQL ===" >> $REPORT_FILE
gcloud run services describe $SERVICE1 --region=$REGION \
    --format="value(spec.template.spec.containers[0].cloudSqlInstances)" >> $REPORT_FILE

echo -e "\n=== $SERVICE2 Cloud SQL ===" >> $REPORT_FILE
gcloud run services describe $SERVICE2 --region=$REGION \
    --format="value(spec.template.spec.containers[0].cloudSqlInstances)" >> $REPORT_FILE

# Compare IAM policies
print_header "IAM Policies"
echo "=== $SERVICE1 IAM Policy ===" >> $REPORT_FILE
gcloud run services get-iam-policy $SERVICE1 --region=$REGION \
    --format=json > ${SERVICE1}_iam.json
cat ${SERVICE1}_iam.json >> $REPORT_FILE

echo -e "\n=== $SERVICE2 IAM Policy ===" >> $REPORT_FILE
gcloud run services get-iam-policy $SERVICE2 --region=$REGION \
    --format=json > ${SERVICE2}_iam.json
cat ${SERVICE2}_iam.json >> $REPORT_FILE

# Compare VPC connector settings
print_header "VPC Connector Settings"
for SERVICE in $SERVICE1 $SERVICE2; do
    echo -e "\n$SERVICE VPC Connector:" >> $REPORT_FILE
    gcloud run services describe $SERVICE \
        --region=$REGION \
        --format="value(spec.template.spec.vpcAccess.connector)" >> $REPORT_FILE
done

# Generate differences summary
print_header "Key Differences Summary"

# Compare container images
IMAGE1=$(gcloud run services describe $SERVICE1 --region=$REGION --format="value(spec.template.spec.containers[0].image)")
IMAGE2=$(gcloud run services describe $SERVICE2 --region=$REGION --format="value(spec.template.spec.containers[0].image)")
if [ "$IMAGE1" != "$IMAGE2" ]; then
    echo "Container images differ:" >> $REPORT_FILE
    echo "  $SERVICE1: $IMAGE1" >> $REPORT_FILE
    echo "  $SERVICE2: $IMAGE2" >> $REPORT_FILE
fi

# Compare IAM policies using diff
echo -e "\nIAM Policy differences:" >> $REPORT_FILE
diff -u ${SERVICE1}_iam.json ${SERVICE2}_iam.json >> $REPORT_FILE 2>&1 || true

# Cleanup temporary files
rm -f ${SERVICE1}_iam.json ${SERVICE2}_iam.json

echo -e "\nAudit report generated: $REPORT_FILE"
echo "Review $REPORT_FILE for detailed comparison"
