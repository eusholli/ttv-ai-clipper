-- Add new workflow-related columns to ingest_jobs table
ALTER TABLE ingest_jobs 
ADD COLUMN IF NOT EXISTS html_fetched_at TIMESTAMP,
ADD COLUMN IF NOT EXISTS html_fetch_success BOOLEAN DEFAULT FALSE,
ADD COLUMN IF NOT EXISTS video_fetched_at TIMESTAMP,
ADD COLUMN IF NOT EXISTS video_fetch_success BOOLEAN DEFAULT FALSE,
ADD COLUMN IF NOT EXISTS metadata_edited_at TIMESTAMP,
ADD COLUMN IF NOT EXISTS transcript_edited_at TIMESTAMP,
ADD COLUMN IF NOT EXISTS workflow_state TEXT DEFAULT 'pending',
ADD COLUMN IF NOT EXISTS last_log_file TEXT;

-- Create table for storing edited metadata
CREATE TABLE IF NOT EXISTS edited_metadata (
    id SERIAL PRIMARY KEY,
    job_id INTEGER REFERENCES ingest_jobs(id),
    title TEXT,
    date TEXT,
    youtube_id TEXT,
    source TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(job_id)
);

-- Create table for storing edited transcripts
CREATE TABLE IF NOT EXISTS edited_transcripts (
    id SERIAL PRIMARY KEY,
    job_id INTEGER REFERENCES ingest_jobs(id),
    segment_hash TEXT NOT NULL,
    text TEXT NOT NULL,
    speaker TEXT,
    company TEXT,
    start_time INTEGER,
    end_time INTEGER,
    subjects TEXT[],
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Add indexes for performance
CREATE INDEX IF NOT EXISTS idx_jobs_workflow_state ON ingest_jobs(workflow_state);
CREATE INDEX IF NOT EXISTS idx_edited_transcripts_job_id ON edited_transcripts(job_id);
CREATE INDEX IF NOT EXISTS idx_edited_metadata_job_id ON edited_metadata(job_id);
