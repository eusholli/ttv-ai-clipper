-- Add 'waiting' to valid workflow states
BEGIN;

-- Temporarily drop the constraint
ALTER TABLE ingest_jobs DROP CONSTRAINT valid_workflow_state;

-- Add new constraint with 'waiting' state
ALTER TABLE ingest_jobs ADD CONSTRAINT valid_workflow_state CHECK (workflow_state IN (
    'pending', 'fetching_html', 'html_fetched', 'editing_metadata',
    'fetching_video', 'video_fetched', 'generating_clips', 'completed', 'failed', 'waiting'
));

COMMIT;
