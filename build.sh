#!/bin/sh

VERSION="1.0.1"
DATE=$(date -u +"%Y-%m-%dT%H:%M:%SZ")
COMMIT=$(git rev-parse --short HEAD 2>/dev/null || echo "no-git")

# Create a backup of the original Dockerfile
cp Dockerfile Dockerfile.bak

# Replace ARG lines with hardcoded values
sed -i '' \
    -e "s|ARG BUILD_VERSION=.*|ARG BUILD_VERSION=\"${VERSION}\"|" \
    -e "s|ARG BUILD_DATE.*|ARG BUILD_DATE=\"${DATE}\"|" \
    -e "s|ARG COMMIT_SHA.*|ARG COMMIT_SHA=\"${COMMIT}\"|" \
    Dockerfile

# Build the Docker image
docker build \
  --build-arg BUILD_VERSION="${VERSION}" \
  --build-arg BUILD_DATE="${DATE}" \
  --build-arg COMMIT_SHA="${COMMIT}" \
  -t ttv-ai-clipper:"${VERSION}" \
  -t ttv-ai-clipper:latest \
  .
