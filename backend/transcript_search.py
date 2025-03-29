# backend/transcript_search.py
import logging
from sentence_transformers import SentenceTransformer
from datetime import datetime
from typing import List, Dict, Any, Optional, Union
import spacy
import torch
from torch.quantization import quantize_dynamic
from backend.database.manager import DatabaseManager


ALL_SUBJECTS = {
    # Notable Technical Terms
    "Bandwidth": "bandwidth",
    "Slice/Slicing": "slice/slicing",
    "Throughput": "throughput",
    "Orchestration": "orchestration",
    "Virtualization": "virtualization",
    "Disaggregation": "disaggregation",
    "Backhaul": "backhaul",
    "Fronthaul": "fronthaul",
    "Roaming": "roaming",
    "API": "api",
    "Fiber": "fiber",
    "Orchestrator": "orchestrator",
    "Automation": "automation",
    
    # Domain-Specific Terms
    "RAN (Radio Access Network)": "ran",
    "MIMO": "mimo",
    "NFV (Network Functions Virtualization)": "nfv",
    "SDN (Software Defined Networking)": "sdn",
    "Telemetry": "telemetry",
    "Containerization": "containerization",
    "Microservices": "microservices",
    "Cloudification": "cloudification",
    "BSS (Business Support Systems)": "bss",
    "OSS (Operations Support Systems)": "oss",
    "QoS (Quality of Service)": "qos",
    "SLA (Service Level Agreement)": "sla"
}

def extract_subject_info(text: str, nlp) -> List[str]:
    # Process input text
    text_doc = nlp(text.lower())
    
    # Get text characteristics
    text_lemmas = {token.lemma_ for token in text_doc if token.is_alpha}
    text_tokens = {token.text for token in text_doc if token.is_alpha}
    text_stems = {token.lemma_[:4] for token in text_doc if token.is_alpha and len(token.lemma_) > 4}  # Get word stems
    
    # Get matched subjects
    matched_subjects = []
    for subject in ALL_SUBJECTS.values():
        # Process subject
        subject_doc = nlp(subject.lower())
        subject_tokens = [token for token in subject_doc if token.is_alpha]
        
        # Skip empty subjects
        if not subject_tokens:
            continue
            
        # Check for matches using multiple methods
        matched = False
        
        # 1. Direct token match
        if any(token.text in text_tokens for token in subject_tokens):
            matched = True
            
        # 2. Lemma match
        if not matched and any(token.lemma_ in text_lemmas for token in subject_tokens):
            matched = True
            
        # 3. Stem match for longer words
        if not matched:
            subject_stems = {token.lemma_[:4] for token in subject_tokens if len(token.lemma_) > 4}
            if subject_stems and subject_stems.intersection(text_stems):
                matched = True
        
        if matched:
            matched_subjects.append(subject)
            
    return matched_subjects

# Configure logging
logger = logging.getLogger(__name__)

class TranscriptSearch:
    def __init__(self):
        """Initialize required extensions"""
        # Initialize database manager
        self.dal = DatabaseManager()
        
        # Initialize models as None for lazy loading
        self._nlp = None
        self._model = None
        self._filter_values = None
        
        # Initialize filter values
        self._filter_values = self.get_available_filters()
 
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

    @staticmethod
    def _create_quantized_spacy():
        """Load and optimize spaCy model"""
        # Load the smallest model
        nlp = spacy.load("en_core_web_sm", disable=["parser", "ner", "textcat"])
        
        # Remove unnecessary pipes
        pipes_to_remove = ["tok2vec", "tagger"]
        for pipe in pipes_to_remove:
            if pipe in nlp.pipe_names:
                nlp.remove_pipe(pipe)
        
        return nlp

    @property
    def nlp(self):
        """Lazy initialization of spaCy model"""
        if self._nlp is None:
            self._nlp = self._create_quantized_spacy()
        return self._nlp

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

        # Use DAL to add transcript
        self.dal.add_transcript_db(
            segment_hash, title, date, youtube_id, source, speaker, company,
            start_time, end_time, duration, subjects, download, text, embedding
        )

    def add_transcripts_batch(self, transcripts: List[Dict[str, Any]]) -> None:
        """
        Batch insert multiple transcripts
        """
        # Generate embeddings for all texts
        texts = [t['text'] for t in transcripts]
        embeddings = self.encode_text(texts)
        
        # Use DAL to add transcripts
        self.dal.add_transcripts_batch_db(transcripts, embeddings)

    def hybrid_search(self,
                     search_text: str,
                     filters: Optional[Dict] = None,
                     semantic_weight: float = 0.5,
                     limit: int = 10) -> List[Dict]:
        """
        Perform hybrid search combining semantic similarity, full-text search, and metadata filtering
        
        Args:
            search_text: The text to search for
            filters: Dictionary of metadata filters:
                - date_range: Tuple[datetime, datetime] - Start and end dates
                - speakers: List[str] - List of speakers to filter on
                - companies: List[str] - List of companies to filter on
                - subjects: List[str] - List of subjects to filter on
                - min_duration: int - Minimum duration
                - max_duration: int - Maximum duration
                - title: str - Filter by partial title match (case-insensitive)
            semantic_weight: Weight given to semantic search vs full-text search (0.0 to 1.0)
            limit: Maximum number of results to return
            
        Returns:
            List of matching transcripts with similarity scores
        """
        # Initialize filters dict if None
        if filters is None:
            filters = {}
            
        # Convert search text to lowercase for case-insensitive matching
        search_text_lower = search_text.lower()
        
        # Check for filter values in search text
        filter_mappings = {
            "speakers": "speakers",
            "companies": "companies"
        }
        
        for filter_key, filter_name in filter_mappings.items():
            found_values = [v for v in self._filter_values[filter_key] 
                          if v and v.lower() in search_text_lower]
            if found_values:
                if filter_name not in filters:
                    filters[filter_name] = found_values
                else:
                    filters[filter_name] = list(set(filters[filter_name] + found_values))
        
        found_subjects = extract_subject_info(search_text_lower, self.nlp)
        if found_subjects:
            if 'subjects' not in filters:
                filters['subjects'] = found_subjects
            else:
                filters['subjects'] = list(set(filters['subjects'] + found_subjects))

        # Generate embedding for semantic search
        search_embedding = self.encode_text(search_text)
        
        # Use DAL to perform search
        return self.dal.hybrid_search_db(search_text, search_embedding, filters, semantic_weight, limit)

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
