-- Add 'waiting' to valid status values
BEGIN;

-- Temporarily drop the constraint
ALTER TABLE ingest_jobs DROP CONSTRAINT valid_status;

-- Add new constraint with 'waiting' status
ALTER TABLE ingest_jobs ADD CONSTRAINT valid_status CHECK (status IN (
    'pending', 'running', 'completed', 'failed', 'deleted', 'waiting'
));

COMMIT;
