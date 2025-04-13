import hashlib
import os
import logging
from datetime import datetime
from typing import List, Dict, Any, Optional
import json # Import json for parsing

# Third-party imports for AI processing
# Removed instructor import
import anthropic
from transformers import pipeline, logging as hf_logging
from pydantic import BaseModel, Field
import psycopg2.extras # For Json adapter

# Local imports
from .constants import MIN_DURATION
from .logging_setup import logger
from .models import TranscriptSegment, Transcript
from backend.transcript_search import TranscriptSearch # Keep for get_segment_hash? Or move hash?
from backend.database.manager import DatabaseManager
from backend.job_manager import JobManager
from backend.r2_manager import R2Manager

# Suppress verbose Hugging Face logging
hf_logging.set_verbosity_error()

# --- Pydantic Model for LLM Extraction Output ---
class ExtractedData(BaseModel):
    """Structure for entities and subjects extracted by LLM."""
    entities: Dict[str, List[str]] = Field(
        default_factory=dict,
        description="Named entities extracted from the text, categorized by type (e.g., {'PERSON': ['John Smith'], 'ORG': ['Tech Corp']})."
    )
    subjects: Optional[List[str]] = Field(
        default_factory=list,
        description="List of main subjects or topics discussed in the text."
    )

class TranscriptDbManager:
    """Handles database operations for transcripts, including enrichment."""

    def __init__(self):
        self.db_manager = DatabaseManager()
        self.job_manager = JobManager()
        self.r2_manager = R2Manager()
        self.ner_model_name = os.getenv("NER_MODEL_NAME", "claude-3-haiku-20240307")
        self.sentiment_model_name = os.getenv("SENTIMENT_MODEL_NAME", "cardiffnlp/twitter-roberta-base-sentiment-latest")

        # Initialize Sentiment Pipeline (Lazy load might be better in Celery context)
        try:
            logger.info(f"Loading sentiment model: {self.sentiment_model_name}")
            # Using device=-1 forces CPU, might be safer in diverse deployment environments
            # unless GPU is guaranteed and configured.
            # Add truncation=True to handle texts longer than model's max length
            self.sentiment_pipeline = pipeline("sentiment-analysis", model=self.sentiment_model_name, device=-1, truncation=True)
            logger.info("Sentiment model loaded successfully.")
        except Exception as e:
            logger.error(f"Failed to load sentiment model '{self.sentiment_model_name}': {e}", exc_info=True)
            self.sentiment_pipeline = None # Allow processing to continue without sentiment

        # Initialize Anthropic Client for NER
        self.anthropic_client = None
        api_key = os.getenv("ANTHROPIC_API_KEY")
        if api_key:
            try:
                logger.info(f"Initializing Anthropic client for NER with model: {self.ner_model_name}")
                # Initialize the standard Anthropic client directly
                self.anthropic_client = anthropic.Anthropic(api_key=api_key) # Keep standard client
                logger.info("Anthropic client initialized successfully (standard client, no instructor).") # Update log message
            except Exception as e:
                logger.error(f"Failed to initialize Anthropic client: {e}", exc_info=True)
                self.anthropic_client = None # Allow processing to continue without NER
        else:
            logger.warning("ANTHROPIC_API_KEY not set. NER processing will be skipped.")

    def process_transcript(self, transcript_obj: Transcript) -> None:
        """Process and store transcript data"""
        # This method seems correct from previous checks, keeping it as is.
        try:
            youtube_id = transcript_obj.metadata.get('youtube_id')

            if youtube_id:
                logger.info(f"Deleting existing entries for YouTube ID: {youtube_id}")
                with self.db_manager.get_write_conn() as conn:
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
                    logger.info(f"Skipping segment \"{segment.text}\"; shorter than {MIN_DURATION} seconds (duration: {duration}s)")
                    continue

                # Create the item dictionary first
                item = {
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
                    'subjects': segment.metadata.get('subjects'), # Use .get for safety
                    'download': segment.metadata.get('download') # Use .get for safety
                }

                # --- Add Sentiment, NER, and Subjects ---
                sentiment_result = self._analyze_sentiment(item['text'])
                # Call the updated extraction method which now returns entities and subjects
                # Use segment.text as it's directly from the loop iteration
                processed_entities, processed_subjects = self._extract_entities_and_subjects(segment.text)

                item['sentiment_score'] = sentiment_result['score']
                item['sentiment_label'] = sentiment_result['label']
                item['entities'] = processed_entities # Assign processed entities
                item['subjects'] = processed_subjects # Assign processed subjects

                # Append the enriched item ONCE
                batch_data.append(item)
            # -----------------------------

            try:
                # Use the database manager to add transcripts
                with self.db_manager.get_write_conn() as conn:
                    with conn.cursor() as cur:
                        # Prepare data for batch insert
                        data = []
                        for item_to_insert in batch_data: # Use different loop var name
                            entities_json = psycopg2.extras.Json(item_to_insert['entities']) if item_to_insert['entities'] is not None else None
                            data.append((
                                item_to_insert['segment_hash'],
                                item_to_insert['title'],
                                item_to_insert['date'],
                                item_to_insert['youtube_id'],
                                item_to_insert['source'],
                                item_to_insert['speaker'],
                                item_to_insert.get('company'),
                                item_to_insert.get('start_time'),
                                item_to_insert.get('end_time'),
                                item_to_insert.get('duration'),
                                item_to_insert.get('subjects'),
                                item_to_insert.get('download'),
                                item_to_insert['text'],
                                None,  # text_vector placeholder
                                # Concatenate fields for full-text search
                                f"{item_to_insert.get('title', '')} {item_to_insert.get('speaker', '')} {item_to_insert.get('company', '')} {item_to_insert.get('text', '')}",
                                # New fields
                                item_to_insert.get('sentiment_score'),
                                item_to_insert.get('sentiment_label'),
                                entities_json
                            ))

                        # Execute batch insert
                        from psycopg2.extras import execute_values
                        execute_values(
                            cur,
                            '''
                            INSERT INTO transcripts (
                                segment_hash, title, date, youtube_id, source, speaker, company,
                                start_time, end_time, duration, subjects, download, text,
                                text_vector, search_vector,
                                sentiment_score, sentiment_label, entities
                            )
                            VALUES %s
                            ''',
                            data,
                            # Updated template for new columns
                            template='''(%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, to_tsvector('english', %s), %s, %s, %s)'''
                        )
                        conn.commit()
                        new_count = len(batch_data)
            except Exception as e:
                logger.warning(f"Batch insert failed: {e}. Falling back to individual inserts.")
                if "duplicate key value" in str(e): # Check if it's specifically a duplicate key error
                    # If we hit duplicates, fall back to individual inserts
                    new_count = 0
                    skipped = 0
                    for item_fallback in batch_data: # Use different loop var name
                        # --- Add Sentiment and NER data to fallback insert ---
                        # Already enriched in batch_data, just access it
                        # ----------------------------------------------------
                        entities_json_fallback = psycopg2.extras.Json(item_fallback['entities']) if item_fallback['entities'] is not None else None

                        try: # Indent try block correctly within the loop
                            with self.db_manager.get_write_conn() as conn:
                                with conn.cursor() as cur:
                                    cur.execute('''
                                        INSERT INTO transcripts (
                                            segment_hash, title, date, youtube_id, source, speaker, company,
                                                start_time, end_time, duration, subjects, download, text,
                                                search_vector, sentiment_score, sentiment_label, entities
                                            )
                                            VALUES (
                                                %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                                                to_tsvector('english', COALESCE(%s, '') || ' ' ||
                                                                     COALESCE(%s, '') || ' ' ||
                                                                     COALESCE(%s, '') || ' ' ||
                                                                     COALESCE(%s, '')),
                                                %s, %s, %s
                                            )
                                        ''', (
                                            item_fallback['segment_hash'],
                                            item_fallback['title'],
                                            item_fallback['date'],
                                            item_fallback['youtube_id'],
                                            item_fallback['source'],
                                            item_fallback['speaker'],
                                            item_fallback.get('company'),
                                            item_fallback.get('start_time'),
                                            item_fallback.get('end_time'),
                                            item_fallback.get('duration'),
                                            item_fallback.get('subjects'),
                                            item_fallback.get('download'),
                                            item_fallback['text'],
                                            item_fallback['title'],
                                            item_fallback['speaker'],
                                            item_fallback.get('company', ''),
                                            item_fallback['text'],
                                            # New fields for fallback
                                            item_fallback.get('sentiment_score'),
                                            item_fallback.get('sentiment_label'),
                                            entities_json_fallback
                                        )) # Ensure closing parenthesis for tuple is here
                                    conn.commit()
                            new_count += 1
                        except psycopg2.errors.UniqueViolation: # Indent except clauses correctly
                            skipped += 1
                            logger.info(f"Skipping duplicate segment during fallback: {item_fallback['segment_hash']}")
                            # No need to rollback here, UniqueViolation doesn't keep transaction open
                        except Exception as e2: # Indent except clauses correctly
                            logger.error(f"Error inserting individual segment {item_fallback['segment_hash']} during fallback: {e2}")
                            # Attempt rollback just in case the connection state is uncertain
                            try:
                                conn.rollback()
                            except Exception as rb_err:
                                logger.error(f"Error during rollback after insert error: {rb_err}")
                            # Decide whether to raise e2 or just log and continue
                            # For robustness, log and continue might be better here
                            # raise e2
                else:
                    raise e

            logger.info(f"Added {new_count} new transcript segments")
            logger.info(f"Skipped {skipped} existing segments")

        except Exception as e:
            logger.error(f"Error processing transcript: {str(e)}")
            raise

    # <<< CORRECTED update_transcripts method >>>
    async def update_transcripts(self, info: Transcript) -> None:
        """Update transcripts table by comparing new entries with existing ones"""
        try:
            youtube_id = info.metadata['youtube_id']
            logger.info(f"Updating transcripts for YouTube ID: {youtube_id}")

            # 1. Fetch existing transcript entries
            existing_entries = []
            with self.db_manager.get_read_conn() as conn:
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
            new_entries_segments = [] # Store segment objects to add
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
                    new_entries_segments.append(segment)
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
                with self.db_manager.get_write_conn() as conn:
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

            # 4. Prepare and enrich remaining new entries
            batch_data = []
            for segment in new_entries_segments: # Iterate through segments to add
                segment_hash = self.get_segment_hash(segment, info.metadata)
                # Define item dictionary correctly for this segment
                item = {
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
                }

                # --- Add Sentiment, NER, and Subjects --- << CORRECTLY PLACED INSIDE LOOP >>
                sentiment_result = self._analyze_sentiment(item['text'])
                # Call the updated extraction method
                # Use item['text'] here as it's within the update_transcripts loop context
                processed_entities, processed_subjects = self._extract_entities_and_subjects(item['text'])

                item['sentiment_score'] = sentiment_result['score']
                item['sentiment_label'] = sentiment_result['label']
                item['entities'] = processed_entities # Assign processed entities
                item['subjects'] = processed_subjects # Assign processed subjects
                # -----------------------------

                # Append the enriched item ONCE
                batch_data.append(item)


            # 5. Insert the enriched batch data
            if batch_data:
                # Use the database manager to add transcripts
                with self.db_manager.get_write_conn() as conn:
                    with conn.cursor() as cur:
                        # Prepare data for batch insert
                        data = []
                        for item_to_insert in batch_data: # Use a different loop variable name
                            entities_json = psycopg2.extras.Json(item_to_insert['entities']) if item_to_insert['entities'] is not None else None
                            data.append((
                                item_to_insert['segment_hash'],
                                item_to_insert['title'],
                                item_to_insert['date'],
                                item_to_insert['youtube_id'],
                                item_to_insert['source'],
                                item_to_insert['speaker'],
                                item_to_insert.get('company'),
                                item_to_insert.get('start_time'),
                                item_to_insert.get('end_time'),
                                item_to_insert.get('duration'),
                                item_to_insert.get('subjects'),
                                item_to_insert.get('download'),
                                item_to_insert['text'],
                                None,  # text_vector placeholder
                                # Concatenate fields for full-text search
                                f"{item_to_insert.get('title', '')} {item_to_insert.get('speaker', '')} {item_to_insert.get('company', '')} {item_to_insert.get('text', '')}",
                                # New fields
                                item_to_insert.get('sentiment_score'),
                                item_to_insert.get('sentiment_label'),
                                entities_json
                            ))

                        # Execute batch insert
                        from psycopg2.extras import execute_values
                        execute_values(
                            cur,
                            '''
                            INSERT INTO transcripts (
                                segment_hash, title, date, youtube_id, source, speaker, company,
                                start_time, end_time, duration, subjects, download, text,
                                text_vector, search_vector,
                                sentiment_score, sentiment_label, entities
                            )
                            VALUES %s
                            ''',
                            data,
                            # Updated template for new columns
                            template='''(%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, to_tsvector('english', %s), %s, %s, %s)'''
                        )
                        conn.commit()
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

    # --- Helper methods for AI processing ---

    def _analyze_sentiment(self, text: str) -> Dict[str, Any]:
        """Analyzes sentiment of the text using the loaded pipeline."""
        default_sentiment = {"label": "neutral", "score": 0.0}
        if not self.sentiment_pipeline or not text:
            return default_sentiment

        try:
            # Transformers pipeline expects a list
            # The pipeline will automatically truncate the text if truncation=True was set
            # For additional safety, we can manually limit text length to avoid tensor size mismatches
            # RoBERTa models typically have a max length of 512 tokens
            max_chars = 500  # Conservative estimate to stay under token limit
            truncated_text = text[:max_chars] if len(text) > max_chars else text
            
            results = self.sentiment_pipeline([truncated_text])
            if results:
                # Map labels if needed (e.g., LABEL_0 -> negative)
                # The specific mapping depends on the model used.
                # For cardiffnlp/twitter-roberta-base-sentiment-latest:
                # LABEL_0: negative, LABEL_1: neutral, LABEL_2: positive
                label_map = {"LABEL_0": "negative", "LABEL_1": "neutral", "LABEL_2": "positive"}
                raw_label = results[0]['label']
                label = label_map.get(raw_label, "neutral") # Default to neutral if mapping fails

                # Adjust score: positive (0 to 1), negative (-1 to 0)
                score = results[0]['score']
                if label == "negative":
                    score = -score # Make negative scores negative

                return {"label": label, "score": score}
            else:
                return default_sentiment
        except Exception as e:
            logger.error(f"Error during sentiment analysis for text '{text[:50]}...': {e}", exc_info=True)
            logger.info(f"Continuing processing with default neutral sentiment due to sentiment analysis error")
            return default_sentiment

    # Renamed method to reflect combined functionality
    def _extract_entities_and_subjects(self, text: str) -> tuple[Optional[Dict[str, List[str]]], Optional[List[str]]]:
        """Extracts named entities and subjects using the Anthropic API."""
        default_return = (None, None)
        if not self.anthropic_client or not text:
            return default_return

        try:
            # Define the prompt for combined extraction
            # Updated schema example in prompt
            system_prompt = f"""
            Analyze the following text segment. Extract:
            1. Named Entities: People (PERSON), Organizations (ORG), and Locations (LOC).
            2. Subjects: A list of the main subjects or topics discussed (e.g., technology, finance, AI).

            Return ONLY a single JSON object conforming to the ExtractedData schema:
            {{"entities": {{"PERSON": ["name1"], "ORG": ["org1"], "LOC": ["loc1"]}}, "subjects": ["subject1", "subject2"]}}

            Ensure the JSON is valid.
            If no entities or subjects are found, return empty structures within the JSON, like:
            {{"entities": {{}}, "subjects": []}}

            Text: "{text}"
            """

            # Make standard API call
            message = self.anthropic_client.messages.create(
                model=self.ner_model_name,
                max_tokens=1024, # Increased tokens slightly for potentially longer output
                messages=[{"role": "user", "content": system_prompt}],
            )

            # Extract the raw text content
            raw_response_content = None
            if message.content and isinstance(message.content, list) and len(message.content) > 0:
                 if hasattr(message.content[0], 'text'):
                      raw_response_content = message.content[0].text

            if not raw_response_content:
                 logger.warning(f"No valid text content found in LLM extraction response for text '{text[:50]}...'")
                 return default_return # Return default tuple

            logger.debug(f"Raw extraction response from Anthropic: {raw_response_content}")

            # Parse the raw JSON string using json.loads and validate with Pydantic
            try:
                # Attempt to find the JSON block if the response isn't pure JSON
                json_start = raw_response_content.find('{')
                json_end = raw_response_content.rfind('}') + 1
                if json_start != -1 and json_end != -1:
                    json_string = raw_response_content[json_start:json_end]
                else:
                    json_string = raw_response_content # Assume it's pure JSON

                parsed_data = json.loads(json_string)
                # Validate against the updated Pydantic model
                extracted_data_obj = ExtractedData(**parsed_data)

                # --- Process Entities ---
                raw_entities = extracted_data_obj.entities
                processed_entities = {}
                if raw_entities: # Check if the dictionary is not None or empty
                    for entity_type, entity_list in raw_entities.items():
                        if entity_list: # Check if the list is not None or empty
                            # Convert to lowercase, remove duplicates using set, then convert back to list
                            lower_unique_entities = list(set(entity.lower() for entity in entity_list if isinstance(entity, str)))
                            processed_entities[entity_type] = lower_unique_entities
                        else:
                            processed_entities[entity_type] = [] # Keep empty list if original was empty
                else:
                     processed_entities = {} # Keep empty dict if original was empty or None

                # --- Process Subjects ---
                raw_subjects = extracted_data_obj.subjects
                processed_subjects = []
                if raw_subjects: # Check if list is not None or empty
                    # Convert to lowercase, remove duplicates using set, then convert back to list
                    processed_subjects = list(set(subj.lower() for subj in raw_subjects if isinstance(subj, str)))

                # Return the processed entities and subjects as a tuple
                return processed_entities, processed_subjects
            except (json.JSONDecodeError, TypeError, ValueError) as parse_error:
                 logger.error(f"Failed to parse Anthropic extraction response into ExtractedData: {parse_error}")
                 logger.error(f"Raw extraction response was: {raw_response_content}")
                 return default_return # Return default tuple on parsing error
        except Exception as e:
            logger.error(f"Error during combined entity/subject extraction for text '{text[:50]}...': {e}", exc_info=True)
            logger.info(f"Continuing processing with default empty entities and subjects due to extraction error")
            return default_return # Return default tuple on error
