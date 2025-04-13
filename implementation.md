# Implementation Recommendation: Enhanced Semantic Search

## 1. Goal

To implement a "Google-like" natural language search experience where users can ask complex questions or use descriptive phrases, and the system retrieves the most semantically relevant segments from video transcripts.

## 2. Rationale

The previous approach parsed queries into concepts and performed hybrid search (concept vector vs. text vector + FTS). This was indirect. The new approach directly compares the semantic meaning of the user's full query against the meaning of smaller, indexed transcript chunks, aligning with modern RAG patterns for better natural language understanding.

## 3. Proposed Solution: Direct Semantic Search via Chunking

1.  **Ingestion:**
    *   **Chunking:** Divide transcripts into smaller chunks using a Recursive Character Splitting strategy (target: 256 tokens, overlap: 50 tokens).
    *   **Chunk Embedding:** Generate embeddings for each *chunk* using `sentence-transformers/paraphrase-MiniLM-L3-v2`.
    *   **Storage:** Store each chunk, its embedding, associated metadata (segment hash, video ID, timestamps, speaker, etc.), and optionally enriched data (sentiment, entities per chunk) in a new `transcript_chunks` table.
2.  **Search:**
    *   **Query Embedding:** Embed the user's *full original query* using the same embedding model.
    *   **Retrieval (Vector Search):** Perform a vector similarity search between the query embedding and the stored chunk embeddings. Retrieve the top N relevant chunks.
    *   **Filtering:** Apply metadata/enrichment filters (speaker, date, sentiment, entities) during the retrieval step. Filters are sourced from UI controls and optionally from LLM parsing of the query.
    *   **Mapping:** Map the retrieved relevant chunks back to their original, full transcript segments based on `segment_hash`.
    *   **Ranking:** Rank the original segments based on the highest similarity score achieved by their constituent chunks.
    *   **Return:** Present the ranked list of original transcript segments to the user.

## 4. Implementation Details

### 4.1. Database Schema (`schema.sql`)

*   A new `transcript_chunks` table will be created to store chunk text, embeddings, timestamps, references to the original segment (`segment_hash`), and denormalized metadata for filtering.
*   The old `transcripts` table will be removed (assuming an empty database start).
*   Appropriate indexes (vector, metadata) will be created on `transcript_chunks`.

### 4.2. Ingestion (`ingest/`, `tasks.py`)

*   A chunking utility using `langchain.text_splitter.RecursiveCharacterTextSplitter` and `tiktoken` will be implemented.
*   The core ingestion task (`process_video_task`) will be modified to:
    *   Chunk original transcript segments.
    *   Generate embeddings for each chunk.
    *   Optionally run enrichment (sentiment/NER) per chunk.
    *   Call a new database method to batch insert chunk data into `transcript_chunks`.

### 4.3. Search (`transcript_search.py`, `database/manager.py`, `query_parser.py`)

*   The `query_parser.py` prompt will be refined to focus on extracting filters, sentiment, and entities, rather than concepts for vector search.
*   `transcript_search.py` will be updated to:
    *   Embed the full `original_query`.
    *   Call a new database function (`search_relevant_chunks_db`) to perform filtered vector search on chunks.
    *   Implement logic to map retrieved chunks back to unique original segments and rank them by the highest chunk similarity score.
*   `database/manager.py` will get the new `search_relevant_chunks_db` function.

### 4.4. Embedding Model

*   Continue using `sentence-transformers/paraphrase-MiniLM-L3-v2` (384 dimensions) initially. Evaluate and consider upgrading if necessary.

### 4.5. Migration

*   No data migration needed as the database is assumed to be empty. Schema will be applied directly.

## 5. Evaluation Metrics

*   Relevance (Human evaluation, benchmark queries)
*   Latency
*   User Satisfaction
