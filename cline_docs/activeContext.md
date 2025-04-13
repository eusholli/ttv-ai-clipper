# Active Context

## Current Work
- **Implemented Direct Semantic Search via Chunking:** Replaced the previous hybrid search logic. The new system involves:
    - **Ingestion:** Chunking transcripts (`RecursiveCharacterTextSplitter`), embedding chunks (`paraphrase-MiniLM-L3-v2`), storing chunks and embeddings in a new `transcript_chunks` table. Optional enrichment (sentiment/NER) can be applied per chunk.
    - **Search:** Embedding the full user query, performing vector similarity search against chunks, applying optional LLM-extracted filters, mapping relevant chunks back to original segments, and ranking segments.
- **Updated Database Schema:** Created `transcript_chunks` table (storing chunk text, embedding, segment hash, timestamps, metadata). Removed the old `transcripts` table (assuming fresh DB). Added appropriate vector and metadata indexes.
- **Refactored Components:** Updated `ingest/` modules (`chunking.py`, `tasks.py`, `transcript_db_manager.py`) for chunking/embedding/storage. Updated `transcript_search.py`, `database/manager.py`, and `query_parser.py` (for filter extraction) to support the new search workflow.

## Recent Changes
- **Direct Semantic Search Implementation:** (Details covered in "Current Work") - This is the most significant recent change, fundamentally altering the search mechanism.
- **Database Schema Overhaul:** Introduced `transcript_chunks` table, removed `transcripts`.
- **Ingestion Pipeline Update:** Integrated chunking (`langchain`, `tiktoken`) and chunk embedding (`sentence-transformers`) into `tasks.py` and related ingestion modules.
- **Search Logic Rewrite:** Updated `transcript_search.py` and `database/manager.py` for chunk-based vector search, filtering, mapping, and ranking.
- **Query Parser Refinement:** Adjusted `query_parser.py` to focus on extracting filters rather than concepts for vector search.
- **Simplified Ingestion (Previous):** Refactored codebase to support **only YouTube URL ingestion**. Removed code related to generic URL processing.
- **Workflow/UI Fixes (Previous):** Addressed issues with UI progress bar and state management for auto-approved YouTube videos.
- **Schema Consolidation (Previous):** Combined all prior migrations into `schema.sql`.
- **Performance Optimizations (Previous):** Added indexes, set statement timeouts.

## Next Steps
1.  **Test Chunking & Embedding:** Verify the ingestion pipeline correctly chunks transcripts, generates embeddings, and stores data in `transcript_chunks`.
2.  **Test Vector Search & Filtering:** Test the core vector search retrieval on `transcript_chunks` with various queries and metadata filters (speaker, date, optional sentiment/entities).
3.  **Test Mapping & Ranking:** Ensure the logic correctly maps retrieved chunks back to original segments and ranks them appropriately based on chunk similarity scores.
4.  **Evaluate Search Relevance:** Perform qualitative evaluation using benchmark queries to assess the relevance of the new search approach compared to the old one.
5.  **Monitor Performance:** Measure ingestion time (chunking/embedding) and search query latency (vector search, filtering, mapping). Optimize vector indexes (`IVFFlat` parameters, etc.) if needed.
6.  **Evaluate Enrichment (If Enabled):** If sentiment/NER is applied per chunk, verify its accuracy and impact on filtering. Monitor associated API costs/latency.
7.  **Refine Chunking Strategy:** Experiment with chunk size and overlap if initial results are suboptimal.
8.  **Update Test Suite:** Add tests covering the chunking process, embedding generation, vector search, filtering, and mapping/ranking logic.
9.  Keep Memory Bank files up to date with project evolution.

## Current State
- **Direct Semantic Search via Chunking:** Backend search logic is implemented based on chunking, embedding, vector search, filtering, and mapping/ranking. Replaced the previous hybrid search.
- **Chunk-Based Ingestion:** Ingestion pipeline processes transcripts into chunks, generates embeddings, and stores them in the `transcript_chunks` table. Optional enrichment per chunk is possible.
- **Database:** Uses `transcript_chunks` table with vector index for search. Old `transcripts` table removed. Schema reflects this new structure.
- **Query Parsing:** LLM (`query_parser.py`) is primarily used for extracting filters from the query, not concepts for direct vector search.
- **Core Workflows:** YouTube URL ingestion, background processing, user auth, etc., remain functional but adapted to the new data structure and search logic.
- **Previous Improvements:** Schema consolidation, performance optimizations (timeouts, indexes), and workflow fixes are still relevant foundations.
