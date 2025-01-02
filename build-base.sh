#!/bin/sh

VERSION="0.0.1"
DATE=$(date -u +"%Y-%m-%dT%H:%M:%SZ")

# Build the Docker image
docker build \
  --build-arg BUILD_VERSION="${VERSION}" \
  --build-arg BUILD_DATE="${DATE}" \
  -t ttv-ai-clipper-base:"${VERSION}" \
  -t ttv-ai-clipper-base:latest \
  -f Dockerfile.base \
  .

docker tag ttv-ai-clipper-base:latest eusholli/ttv-ai-clipper-base:latest
docker push eusholli/ttv-ai-clipper-base:latest
