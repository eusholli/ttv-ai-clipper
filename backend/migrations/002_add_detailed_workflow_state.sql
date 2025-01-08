-- Add detailed workflow state column
ALTER TABLE ingest_jobs ADD COLUMN IF NOT EXISTS detailed_workflow_state TEXT;

-- Update existing jobs with current workflow_state
UPDATE ingest_jobs SET detailed_workflow_state = workflow_state WHERE detailed_workflow_state IS NULL;

-- Add index for workflow state queries
CREATE INDEX IF NOT EXISTS idx_jobs_workflow_state ON ingest_jobs (detailed_workflow_state);
