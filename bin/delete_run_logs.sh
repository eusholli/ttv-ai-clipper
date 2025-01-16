#!/usr/bin/env bash

# Enable command tracing and exit on error
set -ex

REPO_ROOT="$(git rev-parse --show-toplevel)"
cd "$REPO_ROOT"

delete_service_revisions() {
  local service_name=$1
  local project=$2
  echo "Processing service: $service_name in project: $project"
  
  local latest_revision=$(gcloud run services describe "$service_name" \
    --project="$project" \
    --platform=managed \
    --region=us-central1 \
    --format='value(status.latestReadyRevisionName)')
  echo "Latest revision: $latest_revision"
  
  # List all revisions except the latest, sort by creation time (newest first), skip the 5 most recent, then delete the rest
  echo "Listing revisions to delete..."
  gcloud run revisions list --service="$service_name" \
    --project="$project" \
    --platform=managed \
    --region=us-central1 \
    --format="value(metadata.name)" \
    | grep -v "$latest_revision" \
    | sort -r \
    | tail -n +7 \
    | while read -r revision; do
      echo "Deleting revision: $revision"
      gcloud run revisions delete "$revision" \
        --project="$project" \
        --platform=managed \
        --region=us-central1 \
        --quiet
    done
}

# Delete revisions for ttv-ai-clipper
delete_service_revisions "ttv-ai-clipper" "ttv-ai-clipper"

# Delete revisions for staging-ai-clipper
delete_service_revisions "staging-ai-clipper" "staging-ai-clipper"
