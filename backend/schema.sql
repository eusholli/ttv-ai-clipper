-- schema.sql
-- Complete database schema definition for TTV AI Clipper
-- This file represents the final state of the database after all migrations
-- Can be used to initialize a fresh database instance


-- Drop existing objects if they exist
DROP TRIGGER IF EXISTS update_ingest_jobs_updated_at ON ingest_jobs;
DROP FUNCTION IF EXISTS update_updated_at_column();
DROP TABLE IF EXISTS edited_transcripts CASCADE;
DROP TABLE IF EXISTS edited_metadata CASCADE;
DROP TABLE IF EXISTS transcript_chunks CASCADE; -- New table
DROP TABLE IF EXISTS job_transcripts CASCADE;
DROP TABLE IF EXISTS ingest_jobs CASCADE;
DROP TABLE IF EXISTS transcripts CASCADE; -- Keeping original table
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
    search_vector tsvector,    -- for full-text search
    sentiment_score FLOAT,     -- Sentiment score (-1.0 to 1.0 or similar)
    sentiment_label VARCHAR(20), -- e.g., 'positive', 'negative', 'neutral'
    entities JSONB             -- Extracted named entities (e.g., {"PERSON": ["John"], "ORG": ["Acme"]})
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

-- NEW: Transcript Chunks table for storing indexed chunks
CREATE TABLE transcript_chunks (
    chunk_id SERIAL PRIMARY KEY,
    segment_hash TEXT NOT NULL, -- Identifier for the original segment this chunk belongs to (references transcripts.segment_hash)
    youtube_id TEXT NOT NULL,   -- Denormalized for easier filtering
    chunk_text TEXT NOT NULL,
    chunk_vector vector(384) NOT NULL, -- Embedding vector for the chunk_text (using paraphrase-MiniLM-L3-v2 dimension)
    -- Removed estimated chunk_start_time and chunk_end_time
    original_segment_start_time INTEGER NOT NULL, -- Start time of the original segment
    original_segment_end_time INTEGER NOT NULL,   -- End time of the original segment
    speaker TEXT,             -- Denormalized metadata from original segment
    company TEXT,             -- Denormalized metadata from original segment
    date TIMESTAMP,           -- Denormalized metadata from original segment
    sentiment_score FLOAT,    -- Optional: Per-chunk enrichment
    sentiment_label VARCHAR(20), -- Optional: Per-chunk enrichment
    entities JSONB,           -- Optional: Per-chunk enrichment
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
    -- Optional: Add foreign key constraint if desired for strict integrity
    -- CONSTRAINT fk_segment FOREIGN KEY (segment_hash) REFERENCES transcripts(segment_hash) ON DELETE CASCADE
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
CREATE INDEX idx_sentiment_score ON transcripts (sentiment_score); -- Index for filtering/sorting by sentiment
CREATE INDEX idx_entities_gin ON transcripts USING gin(entities); -- GIN index for efficient JSONB querying
CREATE INDEX idx_gin_transcripts_subjects ON transcripts USING GIN (subjects); -- GIN index for efficient subject array querying

-- Create indexes for ingest_jobs table
CREATE INDEX idx_jobs_status ON ingest_jobs (status);
CREATE INDEX idx_jobs_user_email ON ingest_jobs (user_email);
CREATE INDEX idx_jobs_workflow_state ON ingest_jobs (workflow_state);
CREATE INDEX idx_jobs_detailed_workflow_state ON ingest_jobs (detailed_workflow_state);
CREATE INDEX idx_ingest_jobs_id_status ON ingest_jobs (id, status);
CREATE INDEX idx_ingest_jobs_metadata ON ingest_jobs USING gin(metadata);

-- Create indexes for job_transcripts table
CREATE INDEX idx_job_transcripts_created_at ON job_transcripts(created_at);

-- Create indexes for NEW transcript_chunks table
CREATE INDEX idx_chunk_segment_hash ON transcript_chunks (segment_hash); -- To link back
CREATE INDEX idx_chunk_youtube_id ON transcript_chunks (youtube_id); -- For filtering by video
CREATE INDEX idx_chunk_vector ON transcript_chunks USING ivfflat (chunk_vector vector_cosine_ops) WITH (lists = 100); -- Vector index (adjust params if needed)
-- Index on original_segment_start_time might be useful for context/ordering
CREATE INDEX idx_chunk_original_start_time ON transcript_chunks (original_segment_start_time);
CREATE INDEX idx_chunk_speaker ON transcript_chunks (speaker); -- Filter index
CREATE INDEX idx_chunk_company ON transcript_chunks (company); -- Filter index
CREATE INDEX idx_chunk_date ON transcript_chunks (date); -- Filter index
CREATE INDEX idx_chunk_sentiment_label ON transcript_chunks (sentiment_label); -- Filter index
CREATE INDEX idx_chunk_entities_gin ON transcript_chunks USING gin(entities); -- JSONB index

-- Set statement timeouts
ALTER DATABASE CURRENT SET statement_timeout = '30s';
ALTER DATABASE CURRENT SET idle_in_transaction_session_timeout = '30s';

-- Insert initial schema version
-- Incrementing version to reflect schema changes
INSERT INTO schema_version (version) VALUES (12);
