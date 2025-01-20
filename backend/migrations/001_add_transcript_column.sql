-- Add transcript JSONB column to ingest_jobs table
ALTER TABLE ingest_jobs ADD COLUMN transcript JSONB;

-- Update schema version
UPDATE schema_version SET version = 2 WHERE version = 1;
