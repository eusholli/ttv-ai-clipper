#!/usr/bin/env bash

REPO_ROOT="$(git rev-parse --show-toplevel)"
cd "$REPO_ROOT"

VERSION="0.0.8"

# Build the Docker image
docker build \
  --build-arg BUILD_VERSION="${VERSION}" \
  --build-arg ENV_FILE=.env.macbook \
  -t ttv-ai-clipper:"${VERSION}" \
  -t ttv-ai-clipper:latest \
  .
