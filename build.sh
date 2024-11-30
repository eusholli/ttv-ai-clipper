#!/bin/sh

VERSION="1.0.0"
DATE=$(date -u +"%Y-%m-%dT%H:%M:%SZ")
COMMIT=$(git rev-parse --short HEAD 2>/dev/null || echo "no-git")

docker build \
  --build-arg BUILD_VERSION="${VERSION}" \
  --build-arg BUILD_DATE="${DATE}" \
  --build-arg COMMIT_SHA="${COMMIT}" \
  -t my-app:"${VERSION}" \
  -t my-app:latest \
  .
