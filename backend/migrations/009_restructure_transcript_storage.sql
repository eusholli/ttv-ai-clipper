-- Create new job_transcripts table
CREATE TABLE job_transcripts (
    job_id INTEGER PRIMARY KEY REFERENCES ingest_jobs(id),
    transcript JSONB NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- Add new columns to ingest_jobs
ALTER TABLE ingest_jobs
ADD COLUMN metadata JSONB,
ADD COLUMN raw_transcript TEXT;

-- Migrate existing data
WITH extracted_data AS (
    SELECT 
        id,
        transcript->'metadata' as metadata,
        transcript->>'raw_transcript' as raw_transcript,
        transcript as full_transcript
    FROM ingest_jobs
    WHERE transcript IS NOT NULL
)
INSERT INTO job_transcripts (job_id, transcript)
SELECT id, full_transcript
FROM extracted_data;

-- Update ingest_jobs with extracted data
UPDATE ingest_jobs
SET 
    metadata = subquery.metadata,
    raw_transcript = subquery.raw_transcript
FROM (
    SELECT 
        id,
        transcript->'metadata' as metadata,
        transcript->>'raw_transcript' as raw_transcript
    FROM ingest_jobs
    WHERE transcript IS NOT NULL
) as subquery
WHERE ingest_jobs.id = subquery.id;

-- Drop transcript column from ingest_jobs
ALTER TABLE ingest_jobs
DROP COLUMN transcript;

-- Add indexes for performance
CREATE INDEX idx_job_transcripts_created_at ON job_transcripts(created_at);
CREATE INDEX idx_ingest_jobs_metadata ON ingest_jobs USING gin(metadata);

-- Update schema version
INSERT INTO schema_version (version) VALUES (9);
