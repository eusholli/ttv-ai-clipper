#!/bin/sh

gcloud run revisions list --service=ttv-ai-clipper \
  --platform=managed \
  --region=us-central1 \
  --format="value(metadata.name)" \
  | grep -v "$(gcloud run services describe ttv-ai-clipper --platform=managed --region=us-central1 --format='value(status.latestReadyRevisionName)')" \
  | xargs -r gcloud run revisions delete --platform=managed --region=us-central1 --quiet

