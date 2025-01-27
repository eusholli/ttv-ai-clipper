-- Add indexes for better query performance
CREATE INDEX IF NOT EXISTS idx_ingest_jobs_status ON ingest_jobs(status);
CREATE INDEX IF NOT EXISTS idx_ingest_jobs_workflow_state ON ingest_jobs(workflow_state);
CREATE INDEX IF NOT EXISTS idx_ingest_jobs_detailed_workflow_state ON ingest_jobs(detailed_workflow_state);
