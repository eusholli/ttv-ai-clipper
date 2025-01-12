#!/usr/bin/env bash

# Exit on error
set -e

# Print commands before executing
set -x

# Version and project configuration
VERSION="0.0.1"  # Update this version as needed
STAGING_PROJECT_ID="staging-ai-clipper"
IMAGE_NAME="ttv-ai-clipper"
REGION="us-central1"

echo "Starting staging deployment for version ${VERSION}"

# Build the container image
echo "Building container image..."
docker build \
  --platform linux/amd64 \
  -t "gcr.io/${STAGING_PROJECT_ID}/${IMAGE_NAME}:${VERSION}" \
  -t "gcr.io/${STAGING_PROJECT_ID}/${IMAGE_NAME}:latest" \
  .

# Configure docker to use gcloud credentials
echo "Configuring docker authentication..."
gcloud auth configure-docker

# Push the container image to Container Registry with both version and latest tags
echo "Pushing container image with version tag ${VERSION}..."
docker push "gcr.io/${STAGING_PROJECT_ID}/${IMAGE_NAME}:${VERSION}"
echo "Pushing container image with latest tag..."
docker push "gcr.io/${STAGING_PROJECT_ID}/${IMAGE_NAME}:latest"

echo "Deployment completed successfully!"
echo "Image URLs:"
echo "- gcr.io/${STAGING_PROJECT_ID}/${IMAGE_NAME}:${VERSION}"
echo "- gcr.io/${STAGING_PROJECT_ID}/${IMAGE_NAME}:latest"
