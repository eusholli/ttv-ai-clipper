import psycopg2
from psycopg2.extras import execute_values
from sentence_transformers import SentenceTransformer
from datetime import datetime
from typing import List, Dict, Any, Optional, Union
import os
from dotenv import load_dotenv
import spacy
import torch
from torch.quantization import quantize_dynamic


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

class TranscriptSearch:
    def __init__(self):
        """Initialize database connection and required extensions"""
        load_dotenv()
        
        # Check for required environment variables
        required_vars = ['DB_NAME', 'DB_USER', 'DB_PWD', 'DB_HOST']
        missing_vars = [var for var in required_vars if not os.getenv(var)]
        if missing_vars:
            raise EnvironmentError(f"Missing required environment variables: {', '.join(missing_vars)}")
            
        # Check if running in Cloud Run (INSTANCE_CONNECTION_NAME will be set)
        instance_connection_name = os.getenv('INSTANCE_CONNECTION_NAME')
        if instance_connection_name:
            # Use Unix domain socket for Cloud SQL
            db_socket_dir = '/cloudsql'
            cloud_sql_connection_name = os.getenv('INSTANCE_CONNECTION_NAME')
            
            self.conn = psycopg2.connect(
                dbname=os.getenv('DB_NAME'),
                user=os.getenv('DB_USER'),
                password=os.getenv('DB_PWD'),
                host=f'{db_socket_dir}/{cloud_sql_connection_name}',
                connect_timeout=30
            )
        else:
            # Use regular connection for local development
            self.conn = psycopg2.connect(
                dbname=os.getenv('DB_NAME'),
                user=os.getenv('DB_USER'),
                password=os.getenv('DB_PWD'),
                host=os.getenv('DB_HOST'),
                sslmode='require',  # Required for Neon database connections
                connect_timeout=30  # Set connection timeout to 30 seconds
            )
        self.cursor = self.conn.cursor()
        
        # Initialize filter values
        self._filter_values = self._fetch_filter_values()
        # Initialize models as None for lazy loading
        self._nlp = None
        self._model = None
 
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
        # Generate embedding
        # model = SentenceTransformer('all-MiniLM-L6-v2')
        # Generate embedding using quantized model
        embedding = self.encode_text(text)

        try:
            self.cursor.execute('''
                INSERT INTO transcripts (
                    segment_hash, title, date, youtube_id, source, speaker, company,
                    start_time, end_time, duration, subjects, download, text,
                    text_vector, search_vector
                )
                VALUES (
                    %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                    to_tsvector('english', COALESCE(%s, '') || ' ' || 
                                         COALESCE(%s, '') || ' ' || 
                                         COALESCE(%s, '') || ' ' ||
                                         COALESCE(%s, ''))
                )
            ''', (
                segment_hash, title, date, youtube_id, source, speaker, company,
                start_time, end_time, duration, subjects, download, text,
                embedding,
                title, speaker, company, text
            ))
            self.conn.commit()
        except Exception as e:
            self.conn.rollback()
            raise e

    def add_transcripts_batch(self, transcripts: List[Dict[str, Any]]) -> None:
        """
        Batch insert multiple transcripts
        """
        # model = SentenceTransformer('all-MiniLM-L6-v2')
        
        # Generate embeddings for all texts
        texts = [t['text'] for t in transcripts]
        embeddings = self.encode_text(texts)
        
        # Prepare data for batch insert
        data = []
        for transcript, embedding in zip(transcripts, embeddings):
            data.append((
                transcript['segment_hash'],
                transcript['title'],
                transcript['date'],
                transcript['youtube_id'],
                transcript['source'],
                transcript['speaker'],
                transcript.get('company'),
                transcript.get('start_time'),
                transcript.get('end_time'),
                transcript.get('duration'),
                transcript.get('subjects'),
                transcript.get('download'),
                transcript['text'],
                embedding,
                # Concatenate fields for full-text search
                f"{transcript['title']} {transcript['speaker']} {transcript.get('company', '')} {transcript['text']}"
            ))
        
        execute_values(
            self.cursor,
            '''
            INSERT INTO transcripts (
                segment_hash, title, date, youtube_id, source, speaker, company,
                start_time, end_time, duration, subjects, download, text,
                text_vector, search_vector
            )
            VALUES %s
            ''',
            data,
            template='''(%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s::vector, to_tsvector('english', %s))'''
        )
        self.conn.commit()

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
        # model = SentenceTransformer('all-MiniLM-L6-v2')
        search_embedding = self.encode_text(search_text)
        
        # Build the query
        query = '''
            WITH combined_scores AS (
                SELECT 
                    segment_hash,
                    title,
                    date,
                    youtube_id,
                    source,
                    speaker,
                    company,
                    start_time,
                    end_time,
                    duration,
                    subjects,
                    download,
                    text,
                    -- Combine semantic and full-text search scores
                    (
                        %s * (1 - (text_vector <=> %s::vector)) +
                        %s * ts_rank_cd(search_vector, plainto_tsquery('english', %s))
                    ) as similarity
                FROM transcripts
                WHERE 1=1
        '''
        
        params = [
            semantic_weight,
            search_embedding,
            1 - semantic_weight,
            search_text
        ]
        
        # Add filters if provided
        if filters:
            if 'date_range' in filters:
                query += ' AND date BETWEEN %s AND %s'
                params.extend([filters['date_range'][0], filters['date_range'][1]])
            
            # Handle speakers and companies with OR logic when both are present
            if 'speakers' in filters and filters['speakers'] and 'companies' in filters and filters['companies']:
                query += ' AND (speaker = ANY(%s) OR company = ANY(%s))'
                params.extend([filters['speakers'], filters['companies']])
            else:
                # If only one filter is present, use normal AND logic
                if 'speakers' in filters and filters['speakers']:
                    query += ' AND speaker = ANY(%s)'
                    params.append(filters['speakers'])
                if 'companies' in filters and filters['companies']:
                    query += ' AND company = ANY(%s)'
                    params.append(filters['companies'])

            if 'subjects' in filters and filters['subjects']:
                query += ' AND subjects && ARRAY[%s]'
                params.append(filters['subjects'])
                        
            if 'min_duration' in filters:
                query += ' AND duration >= %s'
                params.append(filters['min_duration'])
            
            if 'max_duration' in filters:
                query += ' AND duration <= %s'
                params.append(filters['max_duration'])
                
            if 'title' in filters and filters['title']:
                query += ' AND title ILIKE %s'
                params.append(f'%{filters["title"]}%')
        
        # Complete the query
        query += '''
            )
            SELECT * FROM combined_scores
            ORDER BY similarity DESC
            LIMIT %s;
        '''
        params.append(limit)
        
        # Execute search
        self.cursor.execute(query, params)
        results = self.cursor.fetchall()
        
        # Format results
        formatted_results = []
        for row in results:
            formatted_results.append({
                'segment_hash': row[0],
                'title': row[1],
                'date': row[2],
                'youtube_id': row[3],
                'source': row[4],
                'speaker': row[5],
                'company': row[6],
                'start_time': row[7],
                'end_time': row[8],
                'duration': row[9],
                'subjects': row[10],
                'download': row[11],
                'text': row[12],
                'similarity': row[13]
            })
        
        return formatted_results

    def _fetch_filter_values(self) -> Dict[str, List[str]]:
        """
        Fetch and store unique values for each filterable field from the database
        Returns a dictionary with lists of unique speakers, dates, titles, and companies
        """
        # Get unique speakers
        self.cursor.execute('SELECT DISTINCT speaker FROM transcripts ORDER BY speaker')
        speakers = [row[0] for row in self.cursor.fetchall()]

        # Get unique dates and format them
        self.cursor.execute('''
            SELECT DISTINCT date::date 
            FROM transcripts 
            ORDER BY date DESC
        ''')
        dates = [row[0].strftime("%b %d, %Y") for row in self.cursor.fetchall()]

        # Get unique titles
        self.cursor.execute('SELECT DISTINCT title FROM transcripts ORDER BY title')
        titles = [row[0] for row in self.cursor.fetchall()]

        # Get unique companies
        self.cursor.execute('SELECT DISTINCT company FROM transcripts ORDER BY company')
        companies = [row[0] for row in self.cursor.fetchall() if row[0] is not None]

        # Get unique subjects and create a dictionary mapping display names to values
        self.cursor.execute('SELECT DISTINCT unnest(subjects) FROM transcripts ORDER BY 1')
        db_subjects = [row[0] for row in self.cursor.fetchall() if row[0] is not None]
        
        # Create a dictionary mapping display names to values for subjects found in the database
        # Find display string by matching value in ALL_SUBJECTS
        subjects = {}
        for db_subject in db_subjects:
            for display_str, value in ALL_SUBJECTS.items():
                if value == db_subject:
                    subjects[display_str] = value
                    break

        return {
            "speakers": speakers,
            "dates": dates,
            "titles": titles,
            "companies": companies,
            "subjects": subjects
        }

    def get_metadata_by_hash(self, segment_hash: str) -> Optional[Dict]:
        """
        Get metadata for a specific segment by its hash
        
        Args:
            segment_hash: The hash identifier of the segment
            
        Returns:
            Dictionary containing segment metadata or None if not found
        """
        self.cursor.execute('''
            SELECT 
                segment_hash, title, date, youtube_id, source, speaker, company,
                start_time, end_time, duration, subjects, download, text
            FROM transcripts 
            WHERE segment_hash = %s
        ''', (segment_hash,))
        
        result = self.cursor.fetchone()
        
        if result:
            return {
                'segment_hash': result[0],
                'title': result[1],
                'date': result[2],
                'youtube_id': result[3],
                'source': result[4],
                'speaker': result[5],
                'company': result[6],
                'start_time': result[7],
                'end_time': result[8],
                'duration': result[9],
                'subjects': result[10],
                'download': result[11],
                'text': result[12]
            }
        return None

    def get_available_filters(self) -> Dict[str, List[str]]:
        """
        Returns the stored filter values
        """
        return self._filter_values

    def close(self):
        """Close database connection"""
        self.cursor.close()
        self.conn.close()


# Example usage
def main():
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
    
    search.close()

if __name__ == "__main__":
    main()
