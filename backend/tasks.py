import asyncio
import json
import traceback
from dataclasses import asdict
from celery import Celery
from dotenv import load_dotenv # Import load_dotenv
from backend.ingest.video_processor import VideoProcessor
from backend.ingest.constants import CACHE_DIR, CLIP_DIR
from backend.workflow_processor import WorkflowProcessor
from backend.ingest.transcript_db_manager import TranscriptDbManager
from backend.ingest.chunking import chunk_text # Import the new chunking function
from backend.database.manager import DatabaseManager # Need direct access to DAL
from sentence_transformers import SentenceTransformer # For embeddings
import torch # For sentence transformer
import logging

# Configure logging
logger = logging.getLogger(__name__)

# --- Embedding Model Loading ---
# Load the model once globally or within the task if memory is a concern
# Global loading is generally more efficient for workers processing multiple tasks
try:
    logger.info("Loading sentence transformer model for tasks...")
    # Ensure model is loaded to appropriate device (CPU if no CUDA)
    device = 'cuda' if torch.cuda.is_available() else 'cpu'
    embedding_model = SentenceTransformer('paraphrase-MiniLM-L3-v2', device=device)
    logger.info(f"Sentence transformer model loaded successfully to {device}.")
except Exception as e:
    logger.error(f"Failed to load sentence transformer model: {e}", exc_info=True)
    embedding_model = None

# Load environment variables from .env file at the start
load_dotenv()

# Initialize and configure Celery
celery = Celery('tasks')
celery.config_from_object('backend.celeryconfig')

# Configure logging for Celery tasks
celery.conf.worker_log_format = '[%(asctime)s: %(levelname)s/%(processName)s] %(message)s'
celery.conf.worker_task_log_format = (
    '[%(asctime)s: %(levelname)s/%(processName)s] '
    '[%(task_name)s(%(task_id)s)] %(message)s'
)

@celery.task(bind=True, name='tasks.process_url')
def process_url_task(self, url: str, job_id: int, auto_approve: bool = False):
    """
    Celery task for processing URLs and extracting transcripts.
    
    Args:
        self: Task instance (injected by Celery)
        url: URL to process
        job_id: Job identifier
        auto_approve: Whether to auto-process transcript if parsing is successful
    """
    from backend.ingest.url_processor import UrlProcessor
    
    processor = UrlProcessor(CACHE_DIR)
    workflow_processor = WorkflowProcessor()
    
    try:
        logger.info(f"Starting URL processing for job {job_id}")
        
        # Create and setup event loop
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        try:
            # Process URL and get result
            result = loop.run_until_complete(processor.process_url(url, job_id))
        finally:
            loop.close()
            
        if not result:
            raise Exception("Failed to process URL")
            
        # Update workflow state to editing_metadata if not already done
        # (process_url might have already updated the state)
        db_loop = asyncio.new_event_loop()
        asyncio.set_event_loop(db_loop)
        try:
            # Check current state
            with workflow_processor.dal.get_read_conn() as conn:
                with conn.cursor() as cur:
                    cur.execute('SELECT workflow_state FROM ingest_jobs WHERE id = %s', (job_id,))
                    result = cur.fetchone()
                    current_state = result[0] if result else None
            
            # Only update if not already in editing_metadata or completed state
            if current_state not in ('editing_metadata', 'completed'):
                # Note: This is where we centrally manage state transitions
                # For non-auto-approve jobs, we set to editing_metadata
                # For auto-approve jobs with successful parsing, we'll proceed to video processing
                if not auto_approve:
                    logger.info(f"Standard workflow for job {job_id}, transitioning to editing_metadata")
                    db_loop.run_until_complete(workflow_processor.update_workflow_state(job_id, 'editing_metadata'))
                
            # Check if we should auto-process the transcript
            if auto_approve:
                logger.info(f"Auto-approve enabled for job {job_id}, checking parsing status")
                try:
                    # Get the current parsing status
                    with workflow_processor.dal.get_read_conn() as conn:
                        with conn.cursor() as cur:
                            cur.execute('''
                                SELECT parsing_status
                                FROM ingest_jobs 
                                WHERE id = %s
                            ''', (job_id,))
                            result = cur.fetchone()
                            parsing_status = result[0] if result else None

                    if parsing_status and parsing_status.get('success', False):
                        logger.info(f"Parsing successful, bypassing editing_metadata state and proceeding to video processing")
                        # First update the workflow state to fetching_video to ensure UI updates
                        db_loop.run_until_complete(workflow_processor.update_workflow_state(job_id, 'fetching_video'))
                        # Then start the video processing task
                        db_loop.run_until_complete(workflow_processor.process_transcript(job_id))
                    else:
                        logger.info(f"Parsing failed or not ready, requiring manual review for job {job_id}")
                        # Set to editing_metadata for manual review
                        if current_state not in ('editing_metadata', 'completed'):
                            db_loop.run_until_complete(workflow_processor.update_workflow_state(job_id, 'editing_metadata'))
                except Exception as e:
                    logger.error(f"Error checking parsing status: {str(e)}")
                    # Default to editing_metadata for safety
                    if current_state not in ('editing_metadata', 'completed'):
                        db_loop.run_until_complete(workflow_processor.update_workflow_state(job_id, 'editing_metadata'))
        finally:
            db_loop.close()
            
        return {"success": True, "job_id": job_id}
        
    except Exception as e:
        error_msg = f"Error in URL processing task: {str(e)}\n{traceback.format_exc()}"
        logger.error(error_msg)
        
        # Update workflow state to failed
        error_loop = asyncio.new_event_loop()
        asyncio.set_event_loop(error_loop)
        try:
            error_loop.run_until_complete(workflow_processor.update_workflow_state(job_id, 'failed', error_msg))
        finally:
            error_loop.close()
            
        raise


@celery.task(bind=True, name='tasks.process_video')
def process_video_task(self, info: dict, job_id: int):
    """
    Celery task for processing video content.
    
    Args:
        self: Task instance (injected by Celery)
        info: Video information dictionary
        job_id: Job identifier
    """
    processor = VideoProcessor(CACHE_DIR, CLIP_DIR)
    workflow_processor = WorkflowProcessor()
    # TranscriptDbManager is used for enrichment helpers and potentially saving originals
    transcript_db_manager = TranscriptDbManager()
    # Use DatabaseManager directly for batch inserts
    db_manager = DatabaseManager()
    processor.workflow_processor = workflow_processor

    if embedding_model is None:
        logger.error("Embedding model not loaded. Cannot process video for embeddings.")
        # Update job state to failed
        error_loop = asyncio.new_event_loop()
        asyncio.set_event_loop(error_loop)
        try:
            error_loop.run_until_complete(workflow_processor.update_workflow_state(job_id, 'failed', "Embedding model failed to load"))
        finally:
            error_loop.close()
        raise Exception("Embedding model failed to load")

    try:
        logger.info(f"Starting video processing for job {job_id}")

        # Create and setup event loop for video processing
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

        try:
            # Process video and get result (Transcript object)
            # Assuming result is an instance of backend.ingest.models.Transcript
            result = loop.run_until_complete(processor.process_video(info, job_id))

            # Handle coroutines in transcript metadata if present (remains the same)
            if hasattr(result, 'transcript'):
                for segment in result.transcript:
                    for key, value in segment.metadata.items():
                        if asyncio.iscoroutine(value):
                            logger.info(f"Found coroutine in metadata key {key}")
                            segment.metadata[key] = loop.run_until_complete(value)
        finally:
            loop.close()

        # If we have a valid result with transcript segments, update the database
        if result and hasattr(result, 'transcript') and result.transcript:
            logger.info(f"Video processed. Processing {len(result.transcript)} original segments for job {job_id}.")

            # --- Prepare data for both original segments and chunks ---
            original_segments_batch = []
            chunks_batch = []
            youtube_id = result.metadata.get('youtube_id', '')
            title = result.metadata.get('title', '')
            # Parse date once
            date_str = result.metadata.get('date', '')
            date_obj = None
            if date_str:
                try:
                    # Attempt to parse the date using a method assumed to be in TranscriptDbManager or parse directly
                    # Example direct parsing (adjust format as needed):
                    from datetime import datetime
                    date_obj = datetime.strptime(date_str, '%Y-%m-%d') # Adjust format if needed
                except Exception as e:
                    logger.warning(f"Could not parse date '{date_str}' for job {job_id}: {e}")


            # 1. Process Original Segments (for transcripts table)
            original_texts = [seg.text for seg in result.transcript]
            if original_texts:
                logger.info(f"Generating embeddings for {len(original_texts)} original segments...")
                original_embeddings = embedding_model.encode(original_texts, convert_to_tensor=False, normalize_embeddings=True).tolist()
                logger.info("Embeddings generated for original segments.")

                for i, segment in enumerate(result.transcript):
                    segment_hash = transcript_db_manager.get_segment_hash(segment, result.metadata)
                    start_time = int(segment.metadata['start_timestamp'])
                    end_time = int(segment.metadata['end_timestamp'])

                    # Enrich original segment (optional, but consistent with previous schema)
                    sentiment_result = transcript_db_manager._analyze_sentiment(segment.text)
                    # Call the correct method and unpack the tuple
                    processed_entities, processed_subjects = transcript_db_manager._extract_entities_and_subjects(segment.text)

                    original_segments_batch.append({
                        'segment_hash': segment_hash,
                        'title': title,
                        'date': date_obj,
                        'youtube_id': youtube_id,
                        'source': result.metadata.get('source', ''),
                        'speaker': segment.metadata.get('speaker'),
                        'company': segment.metadata.get('company'),
                        'start_time': start_time,
                        'end_time': end_time,
                        'duration': end_time - start_time,
                        'subjects': processed_subjects, # Use subjects from extraction
                        'download': segment.metadata.get('download'),
                        'text': segment.text,
                        'embedding': original_embeddings[i], # Use pre-generated embedding
                        'sentiment_score': sentiment_result['score'],
                        'sentiment_label': sentiment_result['label'],
                        'entities': processed_entities # Use entities from extraction
                    })

            # 2. Process Chunks (for transcript_chunks table)
            logger.info("Chunking original segments...")
            all_chunk_texts = []
            chunk_metadata_map = [] # To map chunk text back to its metadata

            for segment in result.transcript:
                segment_hash = transcript_db_manager.get_segment_hash(segment, result.metadata)
                original_start_time = int(segment.metadata['start_timestamp'])
                original_end_time = int(segment.metadata['end_timestamp'])

                # Chunk the text of the original segment
                current_chunks = chunk_text(segment.text) # Using default size/overlap from chunking.py

                for chunk_text_item in current_chunks:
                    all_chunk_texts.append(chunk_text_item)
                    # Store metadata needed to create the chunk entry later
                    chunk_metadata_map.append({
                        'segment_hash': segment_hash,
                        'youtube_id': youtube_id,
                        'original_segment_start_time': original_start_time,
                        'original_segment_end_time': original_end_time,
                        'speaker': segment.metadata.get('speaker'),
                        'company': segment.metadata.get('company'),
                        'date': date_obj,
                        'chunk_text': chunk_text_item # Keep text for enrichment
                    })

            if all_chunk_texts:
                logger.info(f"Generating embeddings for {len(all_chunk_texts)} chunks...")
                chunk_embeddings = embedding_model.encode(all_chunk_texts, convert_to_tensor=False, normalize_embeddings=True).tolist()
                logger.info("Embeddings generated for chunks.")

                logger.info(f"Enriching {len(all_chunk_texts)} chunks (Sentiment/NER/Subjects)...")
                for i, chunk_meta in enumerate(chunk_metadata_map):
                    # Enrich chunk text
                    sentiment_result = transcript_db_manager._analyze_sentiment(chunk_meta['chunk_text'])
                    # Call the correct method and unpack the tuple
                    processed_entities, processed_subjects = transcript_db_manager._extract_entities_and_subjects(chunk_meta['chunk_text'])

                    chunks_batch.append({
                        'segment_hash': chunk_meta['segment_hash'],
                        'youtube_id': chunk_meta['youtube_id'],
                        'chunk_text': chunk_meta['chunk_text'],
                        'chunk_vector': chunk_embeddings[i], # Use pre-generated embedding
                        'original_segment_start_time': chunk_meta['original_segment_start_time'],
                        'original_segment_end_time': chunk_meta['original_segment_end_time'],
                        'speaker': chunk_meta.get('speaker'),
                        'company': chunk_meta.get('company'),
                        'date': chunk_meta.get('date'),
                        'sentiment_score': sentiment_result['score'],
                        'sentiment_label': sentiment_result['label'],
                        'entities': processed_entities, # Use entities from extraction
                        'subjects': processed_subjects # Add subjects from extraction
                        # Note: The transcript_chunks table schema might need an update
                        # if it doesn't already have a 'subjects' column.
                        # Assuming for now it exists or will be added.
                    })
                logger.info("Chunk enrichment complete.")


            # --- Database Operations ---
            try:
                # Create new loop for database operations
                db_loop = asyncio.new_event_loop()
                asyncio.set_event_loop(db_loop)
                try:
                    # Delete existing data for this youtube_id first
                    # This prevents issues if reprocessing
                    logger.info(f"Deleting existing segments and chunks for youtube_id: {youtube_id}")
                    with db_manager.get_write_conn() as conn:
                        with conn.cursor() as cur:
                            cur.execute('DELETE FROM transcripts WHERE youtube_id = %s', (youtube_id,))
                            deleted_segments = cur.rowcount
                            cur.execute('DELETE FROM transcript_chunks WHERE youtube_id = %s', (youtube_id,))
                            deleted_chunks = cur.rowcount
                            conn.commit()
                            logger.info(f"Deleted {deleted_segments} existing segments and {deleted_chunks} existing chunks.")

                    # Save original segments (using the existing batch method)
                    if original_segments_batch:
                        logger.info(f"Saving {len(original_segments_batch)} original segments to 'transcripts' table...")
                        # Assuming add_transcripts_batch_db exists and handles embeddings correctly
                        db_manager.add_transcripts_batch_db(original_segments_batch, [s['embedding'] for s in original_segments_batch])
                        logger.info("Original segments saved.")
                    else:
                         logger.info("No original segments to save.")


                    # Save chunks (using the new batch method)
                    if chunks_batch:
                        logger.info(f"Saving {len(chunks_batch)} chunks to 'transcript_chunks' table...")
                        db_manager.add_transcript_chunks_batch_db(chunks_batch)
                        logger.info("Chunks saved.")
                    else:
                        logger.info("No chunks to save.")

                    # Store raw result in job_transcripts and update ingest_jobs metadata (remains the same)
                    result_dict = result.model_dump()
                    logger.info(f"Successfully converted result to dict with keys: {result_dict.keys()}")

                    with db_manager.get_write_conn() as conn:
                        with conn.cursor() as cur:
                            cur.execute('''
                                UPDATE ingest_jobs
                                SET metadata = %s::jsonb,
                                    raw_transcript = %s
                                WHERE id = %s
                            ''', (json.dumps(result.metadata), result.raw_transcript, job_id))

                            cur.execute('''
                                INSERT INTO job_transcripts (job_id, transcript)
                                VALUES (%s, %s::jsonb)
                                ON CONFLICT (job_id)
                                DO UPDATE SET transcript = EXCLUDED.transcript
                            ''', (job_id, result.model_dump_json()))

                            conn.commit()

                    # Mark as completed only after all database operations succeed
                    db_loop.run_until_complete(workflow_processor.update_workflow_state(job_id, 'completed'))
                    return result_dict

                finally:
                    db_loop.close()

            except Exception as db_error:
                error_msg = f"Database operation failed during video processing task for job {job_id}: {str(db_error)}\n{traceback.format_exc()}"
                logger.error(error_msg)
                # Create new loop for error state update
                error_loop = asyncio.new_event_loop()
                asyncio.set_event_loop(error_loop)
                try:
                    error_loop.run_until_complete(workflow_processor.update_workflow_state(job_id, 'failed', error_msg))
                finally:
                    error_loop.close()
                raise # Re-raise the exception to mark the Celery task as failed

        else:
             logger.warning(f"No valid transcript data found in result for job {job_id}. Cannot update database.")
             # Update state to failed as processing didn't yield usable transcript
             error_loop = asyncio.new_event_loop()
             asyncio.set_event_loop(error_loop)
             try:
                 error_loop.run_until_complete(workflow_processor.update_workflow_state(job_id, 'failed', "Video processing completed but no transcript data found."))
             finally:
                 error_loop.close()
             # Return success=False or raise an exception? Raising seems more appropriate.
             raise Exception(f"Video processing completed but no transcript data found for job {job_id}.")


    except Exception as e:
        # Catch exceptions from video processing itself or other parts of the task
        error_msg = f"Error in video processing task for job {job_id}: {str(e)}\n{traceback.format_exc()}"
        logger.error(error_msg)
        # Create new loop for error state update
        error_loop = asyncio.new_event_loop()
        asyncio.set_event_loop(error_loop)
        try:
            # Ensure state is marked as failed
            error_loop.run_until_complete(workflow_processor.update_workflow_state(job_id, 'failed', error_msg))
        finally:
            error_loop.close()
        raise # Re-raise the exception
