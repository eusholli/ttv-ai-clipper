# backend/transcript_search.py
import logging
from sentence_transformers import SentenceTransformer
from datetime import datetime
from typing import List, Dict, Any, Optional, Union
import torch
from torch.quantization import quantize_dynamic
from backend.database.manager import DatabaseManager
from backend.query_parser import get_query_parser # Import the factory
from backend.query_models import ParsedQuery # Import the model for type hinting


# Removed ALL_SUBJECTS dictionary and extract_subject_info function

# Configure logging
logger = logging.getLogger(__name__)

class TranscriptSearch:
    def __init__(self):
        """Initialize required extensions"""
        # Initialize database manager
        self.dal = DatabaseManager()
        # Initialize the query parser using the factory
        self.query_parser = get_query_parser()

        # Initialize embedding model as None for lazy loading
        self._model = None
        # Keep filter values cache if get_available_filters is still used by frontend etc.
        self._filter_values = None
        self._filter_values = self.get_available_filters() # Load initial filters
 
    @staticmethod
    def _create_quantized_transformer():
        """Create a quantized sentence transformer model"""
        model = SentenceTransformer('paraphrase-MiniLM-L3-v2')
        
        # Quantize the model
        if not torch.cuda.is_available():  # Only quantize for CPU
            # Get the underlying transformer model
            transformer_model = model.get_sentence_embedding_dimension()
            if hasattr(model, 'auto_model'):
                # Quantize the linear layers dynamically
                model.auto_model = quantize_dynamic(
                    model.auto_model,
                    {torch.nn.Linear},
                    dtype=torch.qint8
                )
        
        # Set up model for inference mode
        model.eval()  # Set to evaluation mode
        torch.set_grad_enabled(False)  # Disable gradient computation
        
        return model

    # Removed _create_quantized_spacy method
    # Removed nlp property

    @property
    def model(self):
        """Lazy initialization of transformer model"""
        if self._model is None:
            self._model = self._create_quantized_transformer()
        return self._model

    def encode_text(self, text: Union[str, List[str]]) -> List[float]:
        """Encode text with quantized model"""
        # Use the smaller int8 model for inference
        with torch.inference_mode():
            embedding = self.model.encode(
                text,
                convert_to_tensor=False,  # Keep as numpy array
                normalize_embeddings=True  # Normalize to save memory
            )
            # Handle both single text and list of texts
            if isinstance(embedding, list):
                return embedding
            return embedding.tolist()

    def add_transcript(self, 
                      segment_hash: str,
                      text: str,
                      title: str,
                      date: datetime,
                      youtube_id: str,
                      source: str,
                      speaker: str,
                      company: Optional[str] = None,
                      start_time: Optional[int] = None,
                      end_time: Optional[int] = None,
                      duration: Optional[int] = None,
                      subjects: Optional[List[str]] = None,
                      download: Optional[str] = None) -> None:
        """
        Add a single transcript entry with all its metadata
        """
        # Generate embedding using quantized model
        embedding = self.encode_text(text)

        # NOTE: This method might become less relevant as enrichment (sentiment/NER)
        # is now handled in TranscriptDbManager during ingestion.
        # It currently lacks sentiment/entity parameters needed by the updated add_transcript_db.
        # Consider refactoring or removing if add_transcript is always called via TranscriptDbManager.
        logger.warning("TranscriptSearch.add_transcript called directly. Enrichment (sentiment/NER) will be missing.")
        # Use DAL to add transcript (passing None for new fields)
        self.dal.add_transcript_db(
            segment_hash, title, date, youtube_id, source, speaker, company,
            start_time, end_time, duration, subjects, download, text, embedding,
            sentiment_score=None, sentiment_label=None, entities=None
        )

    def add_transcripts_batch(self, transcripts: List[Dict[str, Any]]) -> None:
        """
        Batch insert multiple transcripts
        """
        # Generate embeddings for all texts
        texts = [t['text'] for t in transcripts]
        embeddings = self.encode_text(texts)
        
        # NOTE: Similar to add_transcript, this method might become less relevant.
        # The calling code (likely in TranscriptDbManager) should now handle enrichment
        # before calling the DAL directly or this method needs updating.
        logger.warning("TranscriptSearch.add_transcripts_batch called directly. Enrichment (sentiment/NER) will be missing.")
        # Use DAL to add transcripts (assuming transcripts dicts don't have new fields yet)
        self.dal.add_transcripts_batch_db(transcripts, embeddings)

    # <<< NEW semantic_search implementation >>>
    def semantic_search(self,
                        search_text: str,
                        filters: Optional[Dict] = None,
                        chunk_limit: int = 20, # How many chunks to retrieve initially
                        final_limit: int = 10) -> List[Dict]:
        """
        Performs semantic search by embedding the query and finding similar chunks,
        then maps back to original transcript segments.

        Args:
            search_text: The natural language text to search for.
            filters: Optional dictionary of *additional* metadata filters provided
                     directly (e.g., from UI controls). These supplement any filters
                     identified by the LLM in the search_text.
                - date_range: Tuple[datetime, datetime]
                - speakers: List[str]
                - companies: List[str]
                - sentiment_label: str (e.g., 'positive', 'negative') - from query intent
                - entities: Dict[str, List[str]] - entities mentioned in query
                # Filters like title, duration, subjects apply to original segments,
                # handled after retrieving segments based on chunks.
            chunk_limit: The maximum number of relevant chunks to retrieve from the DB.
            final_limit: The maximum number of final original segments to return.

        Returns:
            List of matching original transcript segments, ranked by relevance,
            with an added 'similarity' score based on the best matching chunk.
        """
        logger.info(f"Performing search for: '{search_text}' with filters: {filters}")

        # --- Handle Filter-Only Search Case ---
        is_filter_only_search = not search_text or search_text.isspace()
        if is_filter_only_search and not filters:
             logger.warning("Both search text and filters are empty. Returning empty results.")
             return []

        # 1. Parse the query to extract potential filters (even if search_text is empty, filters might be in it)
        parsed_query: Optional[ParsedQuery] = None
        try:
            parsed_query = self.query_parser.parse(search_text)
            # --- Added logging to inspect parsed query ---
            logger.info(f"--- INSPECT PARSED QUERY ---: {parsed_query.model_dump_json(indent=2)}")
            # --- End added logging ---
            logger.debug(f"Parsed query for filters: {parsed_query}")
        except Exception as e:
            logger.warning(f"Query parsing failed for '{search_text}', proceeding without LLM-extracted filters: {e}")
            # Create a default ParsedQuery if parsing fails, just holding the original query
            # Use the original search_text even if it's empty/whitespace for consistency
            parsed_query = ParsedQuery(search_concepts=[], original_query=search_text or "")

        # 2. Combine LLM-extracted filters with explicitly provided UI filters
        combined_filters = {}
        if parsed_query and parsed_query.filters:
            combined_filters.update(parsed_query.filters)
        if filters: # Merge explicit UI filters (UI filters might override LLM ones if keys clash)
            combined_filters.update(filters)

        # Add sentiment/entity filters from parsed query if they exist and apply to filter-only search too
        if parsed_query:
            if parsed_query.sentiment_intent and parsed_query.sentiment_intent not in ["objective", "unclear"]:
                 label_map = {"positive": "positive", "negative": "negative", "neutral": "neutral",
                              "happiest": "positive", "most_negative": "negative"}
                 target_label = label_map.get(parsed_query.sentiment_intent)
                 if target_label:
                     combined_filters['sentiment_label'] = target_label
            # REMOVED: Do not automatically add LLM-extracted entities as strict filters
            # for the initial semantic chunk search. They might be used later for display
            # or optional secondary filtering if needed.
            # if parsed_query.entities:
            #      combined_filters['entities'] = parsed_query.entities

        # --- Execute Search ---
        if is_filter_only_search:
            # --- Filter-Only Path ---
            logger.info("Executing filter-only search on original segments.")
            try:
                # Use the new DAL method for filter-only search on 'transcripts' table
                final_results = self.dal.get_segments_by_filters_db(
                    filters=combined_filters,
                    limit=final_limit
                )
                # Add a default score for consistency with semantic search results? Optional.
                for res in final_results:
                    res['score'] = 0.0 # Indicate no semantic similarity calculated
                logger.info(f"Filter-only search returned {len(final_results)} results.")
                return final_results
            except Exception as e:
                logger.error(f"Filter-only search failed in database: {e}", exc_info=True)
                return []
        else:
            # --- Semantic Search Path (Query Text Exists) ---
            logger.info("Executing semantic search on chunks.")
            # 3. Generate embedding for the query (use expanded if available)
            try:
                query_text_to_embed = parsed_query.original_query
                if parsed_query.expanded_query:
                    logger.info(f"Using expanded query for embedding: '{parsed_query.expanded_query}'")
                    query_text_to_embed = parsed_query.expanded_query
                else:
                    logger.info(f"Using original query for embedding: '{parsed_query.original_query}'")

                query_embedding = self.encode_text(query_text_to_embed)
                if not query_embedding:
                     raise ValueError("Generated query embedding is empty.")
            except Exception as e:
                logger.error(f"Failed to encode query text '{parsed_query.original_query}': {e}", exc_info=True)
                return [] # Cannot perform search without query embedding

            logger.debug(f"Combined filters for chunk search: {combined_filters}")

            # 4. Search for relevant chunks in the database
            try:
                relevant_chunks = self.dal.search_relevant_chunks_db(
                    query_embedding=query_embedding,
                    filters=combined_filters, # Pass combined filters here
                    limit=chunk_limit
                )
            except Exception as e:
                logger.error(f"Chunk search failed in database: {e}", exc_info=True)
                return []

            if not relevant_chunks:
                logger.info("No relevant chunks found.")
                return []

            # 5. Map chunks back to unique original segments and determine best score per segment
            segment_scores = {} # {segment_hash: best_similarity}
            unique_segment_hashes = []
            for chunk in relevant_chunks:
                seg_hash = chunk['segment_hash']
                similarity = chunk['similarity']
                if seg_hash not in segment_scores:
                    segment_scores[seg_hash] = similarity
                    unique_segment_hashes.append(seg_hash)
                else:
                    # Update score if this chunk is more similar
                    segment_scores[seg_hash] = max(segment_scores[seg_hash], similarity)

            logger.info(f"Found {len(relevant_chunks)} relevant chunks mapping to {len(unique_segment_hashes)} unique segments.")

            # 6. Retrieve full original segment data
            try:
                original_segments_map = self.dal.get_segments_by_hashes_batch_db(unique_segment_hashes)
            except Exception as e:
                 logger.error(f"Failed to retrieve original segments: {e}", exc_info=True)
                 return [] # Cannot return results without original segment data

            # 7. Combine original segment data with similarity scores and apply final ranking/limit
            final_results = []
            for seg_hash in unique_segment_hashes:
                if seg_hash in original_segments_map:
                    segment_data = original_segments_map[seg_hash]
                    # Add the best similarity score found for this segment
                    segment_data['similarity'] = segment_scores.get(seg_hash, 0.0)
                    final_results.append(segment_data)
                else:
                    logger.warning(f"Original segment data not found for hash: {seg_hash}")

            # Sort final results by similarity score
            final_results.sort(key=lambda x: x.get('similarity', 0.0), reverse=True)

            # Apply final limit
            final_results = final_results[:final_limit]

            logger.info(f"Semantic search returning {len(final_results)} final results.")
            return final_results
    # <<< END NEW semantic_search implementation >>>


    def get_metadata_by_hash(self, segment_hash: str) -> Optional[Dict]:
        """
        Get metadata for a specific segment by its hash
        
        Args:
            segment_hash: The hash identifier of the segment
            
        Returns:
            Dictionary containing segment metadata or None if not found
        """
        return self.dal.get_metadata_by_hash_db(segment_hash)

    def get_available_filters(self) -> Dict[str, List[str]]:
        """
        Returns the stored filter values
        """
        try:
            self._filter_values = self.dal.get_available_filters_db()
            return self._filter_values
        except Exception as e:
            logger.error(f"Error fetching filter values: {str(e)}")
            # If we have cached values, return those instead of failing
            if self._filter_values is not None:
                logger.info("Returning cached filter values due to database error")
                return self._filter_values
            raise

    @classmethod
    def close_pool(cls):
        """Close the connection pool"""
        DatabaseManager().close_pools()
        logger.info("Database connection pools closed")


# Example usage
def main():
    try:
        # Initialize search
        search = TranscriptSearch()
        
        # Add some sample data
        sample_transcripts = [
            {
                'segment_hash': 'abc123',
                'title': 'Tech Talk Q1 2024',
                'date': datetime(2024, 1, 15),
                'youtube_id': 'yt123',
                'source': 'youtube',
                'speaker': 'John Smith',
                'company': 'Tech Corp',
                'start_time': 120,
                'end_time': 180,
                'duration': 60,
                'subjects': ['cloud', 'growth', 'technology'],
                'download': 'https://example.com/video1',
                'text': 'We are seeing strong growth in cloud services across all regions.'
            },
            {
                'segment_hash': 'def456',
                'title': 'AI Summit 2024',
                'date': datetime(2024, 1, 20),
                'youtube_id': 'yt456',
                'source': 'youtube',
                'speaker': 'Jane Doe',
                'company': 'Data Inc',
                'start_time': 45,
                'end_time': 90,
                'duration': 45,
                'subjects': ['AI', 'machine learning', 'innovation'],
                'download': 'https://example.com/video2',
                'text': 'Our AI initiatives are showing promising results in natural language processing.'
            }
        ]
        
        search.add_transcripts_batch(sample_transcripts)
        
        # Perform hybrid search with filters
        results = search.hybrid_search(
            search_text='cloud computing growth',
            filters={
                'date_range': (datetime(2024, 1, 1), datetime(2024, 12, 31)),
                'companies': ['Tech Corp', 'Data Inc'],
                'speakers': ['John Smith', 'Jane Doe'],
                'subjects': ['cloud', 'AI'],
                'source': 'youtube',
                'min_duration': 30,
                'title': 'Tech'  # Will match 'Tech Talk Q1 2024'
            },
            semantic_weight=0.7
        )
        
        # Print results
        for result in results:
            print(f"\nTitle: {result['title']}")
            print(f"Speaker: {result['speaker']} ({result['company']})")
            print(f"Date: {result['date']}")
            print(f"Source: {result['source']} (ID: {result['youtube_id']})")
            print(f"Duration: {result['duration']}s ({result['start_time']}s - {result['end_time']}s)")
            print(f"Subjects: {', '.join(result['subjects'])}")
            print(f"Text: {result['text']}")
            print(f"Similarity: {result['similarity']:.3f}")
            
    except Exception as e:
        logger.error(f"Error in main: {str(e)}")
        raise
    finally:
        # Clean up connection pool
        TranscriptSearch.close_pool()

if __name__ == "__main__":
    main()
