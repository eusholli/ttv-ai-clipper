#!/bin/sh

VERSION="0.0.1"
DATE=$(date -u +"%Y-%m-%dT%H:%M:%SZ")

# Create a backup of the original Dockerfile
cp Dockerfile Dockerfile.bak

# Replace ARG lines with hardcoded values
sed -i '' \
    -e "s|ARG BUILD_VERSION=.*|ARG BUILD_VERSION=\"${VERSION}\"|" \
    -e "s|ARG BUILD_DATE.*|ARG BUILD_DATE=\"${DATE}\"|" \
    Dockerfile

# Build the Docker image
docker build \
  --build-arg BUILD_VERSION="${VERSION}" \
  --build-arg BUILD_DATE="${DATE}" \
  -t ttv-ai-clipper:"${VERSION}" \
  -t ttv-ai-clipper:latest \
  .
