-- Add DELETED to valid workflow states
ALTER TABLE ingest_jobs DROP CONSTRAINT valid_workflow_state;
ALTER TABLE ingest_jobs ADD CONSTRAINT valid_workflow_state 
    CHECK (workflow_state IN ('pending', 'fetching_html', 'html_fetched', 'editing_metadata', 
                            'fetching_video', 'video_fetched', 'generating_clips', 
                            'completed', 'failed', 'deleted'));
