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

    def hybrid_search(self,
                     search_text: str,
                     filters: Optional[Dict] = None,
                     semantic_weight: float = 0.5,
                     limit: int = 10) -> List[Dict]:
        """
        Perform hybrid search using LLM query parsing and enriched index data.

        Args:
            search_text: The natural language text to search for.
            filters: Optional dictionary of *additional* metadata filters provided
                     directly (e.g., from UI controls). These supplement any filters
                     identified by the LLM in the search_text.
                - date_range: Tuple[datetime, datetime]
                - speakers: List[str]
                - companies: List[str]
                # Note: 'subjects' filter might be less relevant now, relying on concepts/entities.
                - min_duration: int - Minimum duration
                - max_duration: int - Maximum duration
                - title: str - Filter by partial title match (case-insensitive)
            semantic_weight: Weight given to semantic search vs full-text search (0.0 to 1.0)
            limit: Maximum number of results to return.

        Returns:
            List of matching transcripts with similarity scores.
        """
        logger.info(f"Performing hybrid search for: '{search_text}' with filters: {filters}")

        # 1. Parse the natural language query using the configured parser
        try:
            parsed_query: ParsedQuery = self.query_parser.parse(search_text)
            logger.debug(f"Parsed query: {parsed_query}")
        except Exception as e:
            logger.error(f"Query parsing failed for '{search_text}': {e}", exc_info=True)
            # Handle error appropriately - maybe return empty list or raise
            # For now, return empty list
            return []

        # 2. Generate embedding for semantic search based on parsed concepts
        # Join concepts into a single string for the encoder
        concepts_text = " ".join(parsed_query.search_concepts) if parsed_query.search_concepts else search_text
        try:
            search_embedding = self.encode_text(concepts_text)
        except Exception as e:
            logger.error(f"Failed to encode concepts '{concepts_text}': {e}", exc_info=True)
            return [] # Cannot perform search without embedding

        # 3. Combine LLM-extracted filters with explicitly provided filters
        # Explicit filters take precedence or are merged.
        final_filters = parsed_query.filters.copy()
        if filters: # Merge explicit filters
            for key, value in filters.items():
                if key in final_filters and isinstance(final_filters[key], list) and isinstance(value, list):
                    # Merge lists and remove duplicates
                    final_filters[key] = list(set(final_filters[key] + value))
                else:
                    # Overwrite or add new filter
                    final_filters[key] = value
        parsed_query.filters = final_filters # Update the ParsedQuery object

        # 4. Use DAL to perform search, passing the entire ParsedQuery object
        try:
            # Note: The DAL method hybrid_search_db needs to be updated
            # to accept ParsedQuery instead of individual arguments.
            # Assuming that update happens in the next step.
            results = self.dal.hybrid_search_db(
                parsed_query=parsed_query, # Pass the structured query object
                search_embedding=search_embedding,
                semantic_weight=semantic_weight,
                limit=limit
            )
            logger.info(f"Hybrid search returned {len(results)} results.")
            return results
        except Exception as e:
            logger.error(f"Database search failed: {e}", exc_info=True)
            return [] # Return empty list on database error

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
