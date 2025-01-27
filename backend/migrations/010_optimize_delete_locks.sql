-- Increase statement timeout for delete operations
ALTER DATABASE CURRENT SET statement_timeout = '30s';

-- Add index to help with locking operations
CREATE INDEX IF NOT EXISTS idx_ingest_jobs_id_status 
ON ingest_jobs (id, status);
