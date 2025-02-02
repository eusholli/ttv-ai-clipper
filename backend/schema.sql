-- schema.sql
-- Complete database schema definition for TTV AI Clipper
-- This file represents the final state of the database after all migrations
-- Can be used to initialize a fresh database instance

-- Wrap everything in a transaction
BEGIN;

-- Drop existing objects if they exist
DROP TRIGGER IF EXISTS update_ingest_jobs_updated_at ON ingest_jobs;
DROP FUNCTION IF EXISTS update_updated_at_column();
DROP TABLE IF EXISTS edited_transcripts CASCADE;
DROP TABLE IF EXISTS edited_metadata CASCADE;
DROP TABLE IF EXISTS job_transcripts CASCADE;
DROP TABLE IF EXISTS ingest_jobs CASCADE;
DROP TABLE IF EXISTS transcripts CASCADE;
DROP TABLE IF EXISTS schema_version CASCADE;

-- Enable required extensions
CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS pg_trgm;

-- Schema version tracking
CREATE TABLE schema_version (
    version INTEGER PRIMARY KEY,
    applied_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- Transcripts table for storing processed transcript data
CREATE TABLE transcripts (
    segment_hash TEXT PRIMARY KEY,
    title TEXT,
    date TIMESTAMP,
    youtube_id TEXT,
    source TEXT,
    speaker TEXT,
    company TEXT,
    start_time INTEGER,
    end_time INTEGER,
    duration INTEGER,
    subjects TEXT[],
    download TEXT,
    text TEXT,
    text_vector vector(384),  -- for semantic search
    search_vector tsvector     -- for full-text search
);

-- Ingest jobs table for tracking video processing workflow
CREATE TABLE ingest_jobs (
    id SERIAL PRIMARY KEY,
    url TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending',
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    error_message TEXT,
    retries INTEGER DEFAULT 0,
    html_fetched_at TIMESTAMP WITH TIME ZONE,
    html_fetch_success BOOLEAN DEFAULT FALSE,
    video_fetched_at TIMESTAMP WITH TIME ZONE,
    video_fetch_success BOOLEAN DEFAULT FALSE,
    metadata_edited_at TIMESTAMP WITH TIME ZONE,
    transcript_edited_at TIMESTAMP WITH TIME ZONE,
    workflow_state TEXT NOT NULL DEFAULT 'pending',
    detailed_workflow_state TEXT,
    last_log_file TEXT,
    user_email TEXT NOT NULL,
    started_at TIMESTAMP WITH TIME ZONE,
    completed_at TIMESTAMP WITH TIME ZONE,
    final_json JSONB,
    parsing_status JSONB,
    metadata JSONB,
    raw_transcript TEXT,
    
    -- Status and workflow state constraints
    CONSTRAINT valid_status CHECK (status IN ('pending', 'running', 'completed', 'failed', 'deleted', 'waiting')),
    CONSTRAINT valid_workflow_state CHECK (workflow_state IN (
        'pending', 'fetching_html', 'html_fetched', 'editing_metadata',
        'fetching_video', 'video_fetched', 'generating_clips', 'completed', 'failed', 'waiting', 'deleted'
    ))
);

-- Create job_transcripts table for storing transcript data
CREATE TABLE job_transcripts (
    job_id INTEGER PRIMARY KEY REFERENCES ingest_jobs(id),
    transcript JSONB NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- Create updated_at trigger function
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$$ language 'plpgsql';

-- Create trigger for ingest_jobs
CREATE TRIGGER update_ingest_jobs_updated_at
    BEFORE UPDATE ON ingest_jobs
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

-- Create indexes for transcripts table
CREATE INDEX idx_speaker_trgm ON transcripts USING gist (speaker gist_trgm_ops);
CREATE INDEX idx_company_trgm ON transcripts USING gist (company gist_trgm_ops);
CREATE INDEX idx_date ON transcripts (date);
CREATE INDEX idx_search_vector ON transcripts USING gin(search_vector);
CREATE INDEX idx_text_vector ON transcripts USING ivfflat (text_vector vector_cosine_ops) WITH (lists = 100);
CREATE INDEX idx_youtube_id ON transcripts (youtube_id);

-- Create indexes for ingest_jobs table
CREATE INDEX idx_jobs_status ON ingest_jobs (status);
CREATE INDEX idx_jobs_user_email ON ingest_jobs (user_email);
CREATE INDEX idx_jobs_workflow_state ON ingest_jobs (workflow_state);
CREATE INDEX idx_jobs_detailed_workflow_state ON ingest_jobs (detailed_workflow_state);
CREATE INDEX idx_ingest_jobs_id_status ON ingest_jobs (id, status);
CREATE INDEX idx_ingest_jobs_metadata ON ingest_jobs USING gin(metadata);

-- Create indexes for job_transcripts table
CREATE INDEX idx_job_transcripts_created_at ON job_transcripts(created_at);

-- Set statement timeouts
ALTER DATABASE CURRENT SET statement_timeout = '30s';
ALTER DATABASE CURRENT SET idle_in_transaction_session_timeout = '30s';

-- Insert initial schema version
INSERT INTO schema_version (version) VALUES (11);

-- Commit the transaction
COMMIT;
