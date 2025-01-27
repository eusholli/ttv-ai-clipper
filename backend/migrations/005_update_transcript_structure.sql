-- Add check constraint to ensure transcript column follows the new structure
ALTER TABLE ingest_jobs
ADD CONSTRAINT transcript_structure_check CHECK (
    transcript IS NULL OR (
        transcript ? 'metadata' AND
        transcript ? 'raw_transcript' AND
        transcript ? 'transcript' AND
        jsonb_typeof(transcript->'metadata') = 'object' AND
        jsonb_typeof(transcript->'raw_transcript') = 'string' AND
        jsonb_typeof(transcript->'transcript') = 'array'
    )
);

-- Add check constraint for required metadata fields
ALTER TABLE ingest_jobs
ADD CONSTRAINT transcript_metadata_check CHECK (
    transcript IS NULL OR (
        transcript->'metadata' ? 'title' AND
        transcript->'metadata' ? 'date' AND
        transcript->'metadata' ? 'youtube_id'
    )
);

-- Migration function to update existing records
CREATE OR REPLACE FUNCTION migrate_transcript_data() RETURNS void AS $$
DECLARE
    job RECORD;
BEGIN
    FOR job IN SELECT id, transcript FROM ingest_jobs WHERE transcript IS NOT NULL LOOP
        -- Create new structure while preserving existing data
        UPDATE ingest_jobs
        SET transcript = jsonb_build_object(
            'metadata', COALESCE(
                job.transcript->'metadata',
                jsonb_build_object(
                    'title', job.transcript->>'title',
                    'date', job.transcript->>'date',
                    'youtube_id', job.transcript->'metadata'->>'youtube_id'
                )
            ),
            'raw_transcript', COALESCE(
                (SELECT string_agg(value->>'text', E'\n')
                 FROM jsonb_array_elements(COALESCE(job.transcript->'transcript', '[]'::jsonb))),
                ''
            ),
            'transcript', COALESCE(job.transcript->'transcript', '[]'::jsonb)
        )
        WHERE id = job.id;
    END LOOP;
END;
$$ LANGUAGE plpgsql;

-- Execute migration
SELECT migrate_transcript_data();

-- Drop migration function after use
DROP FUNCTION migrate_transcript_data();
