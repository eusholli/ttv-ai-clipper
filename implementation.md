# Enhanced AI Search Implementation Plan

## 1. Goal

To replace the current limited search functionality with an advanced AI-powered search capable of understanding natural language queries, including sentiment, intent, entities, and relationships. This implementation will use an API-based LLM (`claude-3-haiku`) for cost-effectiveness and performance, integrated via an abstraction layer.

## 2. Core Components

### 2.1. Query Understanding (API LLM)

*   **Purpose:** Parse the user's natural language search query into a structured format.
*   **Technology:** Anthropic `claude-3-haiku` API via the `anthropic` Python client and the `instructor` library.
*   **Output:** A `ParsedQuery` Pydantic model instance.
*   **Implementation:**
    *   Define `ParsedQuery` model (`backend/query_models.py`).
    *   Create `QueryParser` abstract base class (`backend/query_parser.py`).
    *   Implement `AnthropicQueryParser` subclass (`backend/query_parser.py`).
    *   Configure via environment variables: `QUERY_PARSER_TYPE="anthropic"`, `ANTHROPIC_API_KEY`.

### 2.2. Enhanced Indexing

*   **Purpose:** Enrich transcript data stored in the database during ingestion to support advanced querying.
*   **Database Schema Changes (`schema.sql`, `models.py`):**
    *   Add `sentiment_score FLOAT` to the transcript table (e.g., `job_transcripts`).
    *   Add `sentiment_label VARCHAR(20)` to the transcript table.
    *   Add `entities JSONB` to the transcript table.
*   **Sentiment Analysis:**
    *   **Technology:** Hugging Face `transformers` pipeline with `cardiffnlp/twitter-roberta-base-sentiment-latest`.
    *   **Process:** During ingestion (e.g., in `backend/tasks.py` or `content_processor.py`), calculate sentiment for each transcript segment and store the score and label.
*   **Named Entity Recognition (NER):**
    *   **Technology:** Anthropic `claude-3-haiku` API via `instructor`.
    *   **Process:** During ingestion, call the API for each transcript segment with a prompt to extract entities (PERSON, ORG, etc.) and store the resulting JSON in the `entities` column.
*   **Database Manager (`database/manager.py`):** Update `add_transcript_db` and `add_transcripts_batch_db` to accept and store the new sentiment and entity data.

### 2.3. Modified Search Logic

*   **Purpose:** Utilize the structured query and enhanced index data for searching.
*   **`transcript_search.py` (`hybrid_search`):**
    *   Instantiate the configured `AnthropicQueryParser`.
    *   Call `parser.parse(search_text)` to get the `ParsedQuery` object.
    *   Pass the `ParsedQuery` object to `dal.hybrid_search_db`.
*   **`database/manager.py` (`hybrid_search_db`):**
    *   Modify function signature to accept `parsed_query: ParsedQuery`.
    *   Construct SQL query dynamically based on `ParsedQuery` fields:
        *   Vector search using embeddings from `parsed_query.search_concepts`.
        *   Full-text search potentially using `parsed_query.search_concepts` or terms from `parsed_query.relationships`.
        *   Filter by `sentiment_score` based on `parsed_query.sentiment_intent`.
        *   Filter by `entities` using JSONB operators (`@>`) based on `parsed_query.entities`.
        *   Apply standard metadata filters from `parsed_query.filters`.
        *   Handle `parsed_query.relationships` logic (e.g., requiring co-occurrence of terms).

## 3. Implementation Steps

1.  **Create `implementation.md` (This file).**
2.  **Define `ParsedQuery` Model:** Create `backend/query_models.py` with the Pydantic model.
3.  **Implement Query Parser:** Create `backend/query_parser.py` with the abstract class and `AnthropicQueryParser`.
4.  **Update Dependencies:** Add `anthropic`, `instructor`, `transformers[torch]`, `accelerate` to `backend/requirements.txt`. Install them.
5.  **Update Database Schema:** Modify `backend/schema.sql` to add `sentiment_score`, `sentiment_label`, and `entities` columns to the appropriate table (likely `job_transcripts` or similar). Apply changes (e.g., re-run `init_db.sh` or create a migration script).
6.  **Update ORM/Models:** Modify `backend/models.py` (if using an ORM) or relevant data structures to reflect the new schema.
7.  **Update DB Manager (Insert):** Modify `add_transcript_db` and `add_transcripts_batch_db` in `backend/database/manager.py` to handle the new columns.
8.  **Integrate Sentiment Analysis:** Modify the ingestion task (`backend/tasks.py` or `content_processor.py`) to load the RoBERTa model and calculate/pass sentiment data when calling the DB manager's add methods.
9.  **Integrate NER:** Modify the ingestion task to call the Anthropic API (`claude-3-haiku`) for each segment, parse the entity JSON, and pass it when calling the DB manager's add methods. Ensure API key is available to Celery workers.
10. **Modify Search Entrypoint:** Update `hybrid_search` in `backend/transcript_search.py` to use the `AnthropicQueryParser` and pass the `ParsedQuery` object to the DAL.
11. **Modify DB Manager (Search):** Update `hybrid_search_db` in `backend/database/manager.py` to accept `ParsedQuery` and implement the new SQL query logic.
12. **Cleanup:** Remove `ALL_SUBJECTS`, `extract_subject_info`, and naive filter extraction from `backend/transcript_search.py`.
13. **Testing:** Thoroughly test with various complex queries, including sentiment, entity, and relationship-based searches. Test ingestion process.
14. **Update Memory Bank:** Update `cline_docs/systemPatterns.md`, `cline_docs/techContext.md`, `cline_docs/activeContext.md`, `cline_docs/progress.md`.

## 4. Configuration

*   **Environment Variables:**
    *   `QUERY_PARSER_TYPE="anthropic"`
    *   `ANTHROPIC_API_KEY="sk-ant-..."` (Ensure this is available to both FastAPI and Celery services)
    *   (Optional) `SENTIMENT_MODEL_NAME="cardiffnlp/twitter-roberta-base-sentiment-latest"`
    *   (Optional) `NER_MODEL_NAME="claude-3-haiku-20240307"` (or specific version)

## 5. Deployment Considerations (Cloud Run)

*   Ensure both FastAPI and Celery worker services have the `ANTHROPIC_API_KEY` set.
*   Ensure services have outbound network access to `api.anthropic.com`.
*   The Hugging Face sentiment model will be downloaded during the container build or on first use (consider caching in the container image).
*   Monitor API usage costs for Anthropic.
