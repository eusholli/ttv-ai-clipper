-- Add final_json column to ingest_jobs table
ALTER TABLE ingest_jobs ADD COLUMN final_json JSONB;

-- Update schema version
INSERT INTO schema_version (version) VALUES (4);
