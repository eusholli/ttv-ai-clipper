import hashlib
from datetime import datetime
from typing import List, Dict, Any

from .constants import MIN_DURATION

from .logging_setup import logger
from .models import TranscriptSegment, Transcript
from backend.transcript_search import TranscriptSearch
from backend.job_manager import JobManager
from backend.r2_manager import R2Manager

class TranscriptDbManager:
    """Handles database operations for transcripts"""

    def __init__(self):
        self.search = TranscriptSearch()
        self.job_manager = JobManager()
        self.r2_manager = R2Manager()

    def process_transcript(self, transcript_obj: Transcript) -> None:
        """Process and store transcript data"""
        try:
            youtube_id = transcript_obj.metadata.get('youtube_id')
            
            if youtube_id:
                logger.info(f"Deleting existing entries for YouTube ID: {youtube_id}")
                with self.search.get_db_connection() as conn:
                    with conn.cursor() as cur:
                        cur.execute('DELETE FROM transcripts WHERE youtube_id = %s', (youtube_id,))
                        conn.commit()
                
                # Mark associated jobs as deleted
                logger.info(f"Marking jobs as deleted for YouTube ID: {youtube_id}")
                self.job_manager.mark_job_deleted(youtube_id)
            
            new_count = 0
            skipped = 0
            
            logger.info(f"Processing transcript with {len(transcript_obj.transcript)} segments...")
            
            # Parse date string to datetime object if exists
            date_str = transcript_obj.metadata.get('date', '')
            date = None
            if date_str:
                try:
                    # Try different date formats
                    date_formats = ['%Y-%m-%d', '%b %d, %Y']
                    for fmt in date_formats:
                        try:
                            date = datetime.strptime(date_str, fmt)
                            break
                        except ValueError:
                            continue
                    if date is None:
                        logger.warning(f"Could not parse date: {date_str}")
                except Exception as e:
                    logger.warning(f"Error parsing date '{date_str}': {str(e)}")

            # Prepare batch data
            batch_data = []
            
            for segment in transcript_obj.transcript:
                segment_hash = self.get_segment_hash(segment, transcript_obj.metadata)
                start_time = int(segment.metadata['start_timestamp'])
                end_time = int(segment.metadata['end_timestamp'])
                duration = end_time - start_time
                
                # Skip segments less than MIN_DURATION seconds
                if duration < MIN_DURATION:
                    logger.info(f"Skipping segment \"{segment['text']}\"; shorter than {MIN_DURATION} seconds (duration: {duration}s)")
                    continue
                
                batch_data.append({
                    'segment_hash': segment_hash,
                    'text': segment.text,
                    'title': transcript_obj.metadata.get('title', ''),
                    'date': date,
                    'youtube_id': transcript_obj.metadata.get('youtube_id', ''),
                    'source': transcript_obj.metadata.get('source', ''),
                    'speaker': segment.metadata['speaker'],
                    'company': segment.metadata['company'],
                    'start_time': start_time,
                    'end_time': end_time,
                    'duration': end_time - start_time,
                    'subjects': segment.metadata['subjects'],
                    'download': segment.metadata['download']
                })
            
            try:
                self.search.add_transcripts_batch(batch_data)
                new_count = len(batch_data)
            except Exception as e:
                if "duplicate key value" in str(e):
                    # If we hit duplicates, fall back to individual inserts
                    new_count = 0
                    skipped = 0
                    for data in batch_data:
                        try:
                            self.search.add_transcript(**data)
                            new_count += 1
                        except Exception as e2:
                            if "duplicate key value" in str(e2):
                                skipped += 1
                                logger.info(f"Skipping duplicate segment: {data['segment_hash']}")
                            else:
                                raise e2
                else:
                    raise e
            
            logger.info(f"Added {new_count} new transcript segments")
            logger.info(f"Skipped {skipped} existing segments")
            
        except Exception as e:
            logger.error(f"Error processing transcript: {str(e)}")
            raise

    async def update_transcripts(self, info: Transcript) -> None:
        """Update transcripts table by comparing new entries with existing ones"""
        try:
            youtube_id = info.metadata['youtube_id']
            logger.info(f"Updating transcripts for YouTube ID: {youtube_id}")

            # 1. Fetch existing transcript entries
            existing_entries = []
            with self.search.get_db_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute('''
                        SELECT speaker, company, text, start_time, end_time, download
                        FROM transcripts 
                        WHERE youtube_id = %s
                    ''', (youtube_id,))
                    existing_entries = cur.fetchall()

            # Convert existing entries to set of tuples for comparison
            existing_set = {(e[0], e[1], e[2], e[3], e[4], e[5]) for e in existing_entries}
            
            # Convert new entries to comparable format and track which to keep
            new_entries = []
            for segment in info.transcript:
                entry_tuple = (
                    segment.metadata['speaker'],
                    segment.metadata['company'],
                    segment.text,
                    segment.metadata['start_timestamp'],
                    segment.metadata['end_timestamp'],
                    segment.metadata['download']
                )
                if entry_tuple not in existing_set:
                    new_entries.append(segment)
                else:
                    # Remove from existing set if found in new entries
                    existing_set.remove(entry_tuple)

            # 3. Delete remaining existing entries and their clips
            for entry in existing_set:
                clip_name = entry[5]  # download field contains clip filename
                if clip_name:
                    logger.info(f"Deleting clip from R2: {clip_name}")
                    truncated_clip_name = clip_name.split('/')[-1]
                    self.r2_manager.delete_file(truncated_clip_name)

            # Delete only the entries that remain in existing_set
            if existing_set:
                with self.search.get_db_connection() as conn:
                    with conn.cursor() as cur:
                        # Build the WHERE clause for the specific entries to delete
                        delete_conditions = []
                        delete_params = []
                        for entry in existing_set:
                            delete_conditions.append("(start_time = %s AND end_time = %s)")
                            delete_params.extend([entry[3], entry[4]])
                        
                        # Combine all conditions with OR and add youtube_id check
                        delete_query = f"""
                            DELETE FROM transcripts 
                            WHERE youtube_id = %s 
                            AND ({' OR '.join(delete_conditions)})
                        """
                        delete_params.insert(0, youtube_id)
                        
                        cur.execute(delete_query, delete_params)
                        deleted_count = cur.rowcount
                        logger.info(f"Deleted {deleted_count} existing transcript entries")
                        conn.commit()

            # 4. Add remaining new entries
            batch_data = []
            for segment in new_entries:
                segment_hash = self.get_segment_hash(segment, info.metadata)
                batch_data.append({
                    'segment_hash': segment_hash,
                    'text': segment.text,
                    'title': info.metadata.get('title', ''),
                    'date': datetime.strptime(info.metadata.get('date', ''), '%Y-%m-%d') if info.metadata.get('date') else None,
                    'youtube_id': youtube_id,
                    'source': info.metadata.get('source', ''),
                    'speaker': segment.metadata['speaker'],
                    'company': segment.metadata['company'],
                    'start_time': int(segment.metadata['start_timestamp']),
                    'end_time': int(segment.metadata['end_timestamp']),
                    'duration': int(segment.metadata['end_timestamp']) - int(segment.metadata['start_timestamp']),
                    'subjects': segment.metadata.get('subjects'),
                    'download': segment.metadata.get('download')
                })

            if batch_data:
                self.search.add_transcripts_batch(batch_data)
                logger.info(f"Added {len(batch_data)} new transcript segments")

        except Exception as e:
            logger.error(f"Error updating transcripts: {str(e)}")
            raise

    def get_segment_hash(self, segment: TranscriptSegment, main_metadata: dict) -> str:
        """Generate hash for transcript segment"""
        hash_string = (
            f"{segment.text}"
            f"{segment.metadata['start_timestamp']}"
            f"{segment.metadata['end_timestamp']}"
            f"{main_metadata.get('title', '')}"
            f"{main_metadata.get('date', '')}"
        )
        return hashlib.md5(hash_string.encode()).hexdigest()
