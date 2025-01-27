-- Add transcript column back to ingest_jobs
ALTER TABLE ingest_jobs
ADD COLUMN transcript JSONB;

-- Migrate data back from job_transcripts
UPDATE ingest_jobs i
SET transcript = jt.transcript
FROM job_transcripts jt
WHERE i.id = jt.job_id;

-- Drop new columns from ingest_jobs
ALTER TABLE ingest_jobs
DROP COLUMN metadata,
DROP COLUMN raw_transcript;

-- Drop job_transcripts table
DROP TABLE job_transcripts;

-- Update schema version
DELETE FROM schema_version WHERE version = 9;
