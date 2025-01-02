#!/bin/sh

VERSION="0.0.1"
DATE=$(date -u +"%Y-%m-%dT%H:%M:%SZ")

# Create and use a new builder instance that supports multi-platform builds
docker buildx create --use

# Build and push multi-platform image directly
docker buildx build \
  --platform linux/amd64,linux/arm64 \
  --build-arg BUILD_VERSION="${VERSION}" \
  --build-arg BUILD_DATE="${DATE}" \
  -t eusholli/ttv-ai-clipper-base:latest \
  -t eusholli/ttv-ai-clipper-base:"${VERSION}" \
  -f Dockerfile.base \
  --push \
  .
