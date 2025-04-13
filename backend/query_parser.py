# Removed instructor import
import anthropic
import os
import logging
from abc import ABC, abstractmethod
from typing import Type
import json # Import json for parsing
from backend.query_models import ParsedQuery
from dotenv import load_dotenv # Import load_dotenv

# Configure logging
logger = logging.getLogger(__name__)

# Load environment variables from .env file at the start
load_dotenv()

# --- Abstract Base Class ---

class QueryParser(ABC):
    """Abstract base class for query parsers."""

    @abstractmethod
    def parse(self, query_text: str) -> ParsedQuery:
        """
        Parses the natural language query text into a structured ParsedQuery object.

        Args:
            query_text: The user's raw search query.

        Returns:
            A ParsedQuery object representing the structured understanding of the query.

        Raises:
            NotImplementedError: If the method is not implemented by a subclass.
            Exception: If parsing fails.
        """
        raise NotImplementedError


# --- Anthropic Implementation ---

class AnthropicQueryParser(QueryParser):
    """Query parser using the Anthropic API (Claude) and instructor."""

    def __init__(self, api_key: str = None, model: str = "claude-3-haiku-20240307"):
        """
        Initializes the Anthropic client with instructor patching.

        Args:
            api_key: Anthropic API key. Reads from ANTHROPIC_API_KEY env var if None.
            model: The Anthropic model to use (defaults to claude-3-haiku).
        """
        resolved_api_key = api_key or os.getenv("ANTHROPIC_API_KEY")
        if not resolved_api_key:
            raise ValueError("Anthropic API key not provided or found in environment variables (ANTHROPIC_API_KEY).")

        try:
            # Initialize the standard Anthropic client directly
            self.client = anthropic.Anthropic(api_key=resolved_api_key)
            self.model = model
            logger.info(f"AnthropicQueryParser initialized with model: {self.model} (standard client, no instructor)")
        except Exception as e:
            logger.error(f"Failed to initialize Anthropic client: {e}")
            raise

    def parse(self, query_text: str) -> ParsedQuery:
        """
        Parses the query using the configured Anthropic model.

        Args:
            query_text: The user's raw search query.

        Returns:
            A ParsedQuery object.

        Raises:
            Exception: If the API call fails or parsing is unsuccessful.
        """
        logger.debug(f"Parsing query with Anthropic ({self.model}): '{query_text}'")
        try:
            # Define the prompt for the LLM
            # This prompt guides the LLM to extract information matching the ParsedQuery schema.
            # It explicitly asks for concepts, sentiment/intent, entities, filters, and relationships.
            system_prompt = f"""
            Analyze the user's search query for video clips and extract filtering criteria and intent into the provided JSON schema.
            The primary search will be semantic based on the full query text, but this extraction helps apply filters.

            Query: "{query_text}"

            Instructions:
            1.  **search_concepts**: [DEPRECATED - No longer primary driver for vector search]. Briefly list main topics if obvious, but focus on other fields. Return empty list if unsure.
            2.  **sentiment_intent**: Determine the overall sentiment or intent expressed *in the query*. Choose ONE from: 'positive', 'negative', 'neutral', 'happiest', 'most_negative', 'objective', 'unclear'. 'objective' is the default if no clear sentiment is expressed. This will be used for filtering results based on analyzed segment sentiment.
            3.  **entities**: Extract named entities mentioned IN THE QUERY ITSELF (people, organizations, locations, specific products/terms if relevant). Categorize them (e.g., PERSON, ORG). This will be used for filtering results based on entities found in segments. If none, return empty dict.
            4.  **filters**: Identify explicit or implicit metadata filters mentioned IN THE QUERY (e.g., specific speakers, companies, date constraints like "last week", "in 2023"). Do NOT infer filters from general topics. If none, return empty dict.
            5.  **relationships**: [DEPRECATED - Less relevant now]. Briefly describe relationships if very clear, otherwise return null.
            6.  **original_query**: Include the original user query verbatim.

            Return ONLY the JSON object conforming to the ParsedQuery schema. Ensure the JSON is valid.
            """

            # Make standard API call without response_model
            message = self.client.messages.create(
                model=self.model,
                max_tokens=1024,
                messages=[{"role": "user", "content": system_prompt}],
            )

            # Extract the raw text content (assuming it's the JSON string)
            # Anthropic response structure might vary, adjust access as needed
            raw_response_content = None
            if message.content and isinstance(message.content, list) and len(message.content) > 0:
                 # Assuming the response is in the first block and is text
                 if hasattr(message.content[0], 'text'):
                      raw_response_content = message.content[0].text

            if not raw_response_content:
                 raise Exception("Failed to get valid content from Anthropic API response.")

            logger.debug(f"Raw response from Anthropic: {raw_response_content}")

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
                parsed_query_obj = ParsedQuery(**parsed_data)
                # Ensure original_query is set correctly
                if not hasattr(parsed_query_obj, 'original_query') or not parsed_query_obj.original_query:
                    parsed_query_obj.original_query = query_text
                logger.debug(f"Successfully parsed query: {parsed_query_obj}")
                return parsed_query_obj
            except (json.JSONDecodeError, TypeError, ValueError) as parse_error:
                 logger.error(f"Failed to parse Anthropic response into ParsedQuery: {parse_error}")
                 logger.error(f"Raw response was: {raw_response_content}")
                 raise Exception(f"Failed to parse Anthropic response: {parse_error}") from parse_error

            # --- Attempt Query Expansion (Optional Second LLM Call) ---
            try:
                expansion_prompt = f"""
                Given the user's original search query for video clips related to telecom and technology:
                "{parsed_query_obj.original_query}"

                Expand or rephrase this query to potentially improve semantic search recall. Focus on adding relevant synonyms, related concepts, or clarifying the intent based on the likely domain.
                Return ONLY the expanded/rephrased query text, without any preamble or explanation.
                If the original query is already clear and concise, you can return it unchanged.
                """
                expansion_message = self.client.messages.create(
                    model=self.model, # Use the same model for consistency
                    max_tokens=512, # Shorter response needed
                    messages=[{"role": "user", "content": expansion_prompt}],
                )

                expanded_query_text = None
                if expansion_message.content and isinstance(expansion_message.content, list) and len(expansion_message.content) > 0:
                    if hasattr(expansion_message.content[0], 'text'):
                        expanded_query_text = expansion_message.content[0].text.strip()

                if expanded_query_text:
                    # Only assign if expansion is different and not empty
                    if expanded_query_text != parsed_query_obj.original_query and expanded_query_text:
                        parsed_query_obj.expanded_query = expanded_query_text
                        logger.debug(f"Generated expanded query: {expanded_query_text}")
                    else:
                        logger.debug("Expansion resulted in the same or empty query, not storing.")
                else:
                     logger.warning("Failed to get valid content from Anthropic API response for query expansion.")

            except Exception as expansion_error:
                logger.warning(f"Optional query expansion failed: {expansion_error}", exc_info=False) # Log as warning, don't fail the whole parse

            return parsed_query_obj # Return the object, potentially with expanded_query populated

        except Exception as e:
            logger.error(f"Error parsing query with Anthropic: {e}")
            # Consider returning a default/error ParsedQuery or re-raising
            # For now, re-raise to indicate failure
            raise Exception(f"Failed to parse query using Anthropic API: {e}") from e


# --- Factory Function (Optional but Recommended) ---

def get_query_parser() -> QueryParser:
    """
    Factory function to instantiate the appropriate query parser based on environment variables.
    """
    parser_type = os.getenv("QUERY_PARSER_TYPE", "anthropic").lower()
    logger.info(f"Attempting to load query parser of type: {parser_type}")

    if parser_type == "anthropic":
        try:
            return AnthropicQueryParser()
        except ValueError as e:
            logger.error(f"Configuration error for AnthropicQueryParser: {e}")
            raise # Re-raise configuration errors
        except Exception as e:
            logger.error(f"Failed to initialize AnthropicQueryParser: {e}")
            raise # Re-raise initialization errors
    # Add other parser types here later (e.g., "openai", "local_llm")
    # elif parser_type == "local_llm":
    #     endpoint = os.getenv("LOCAL_LLM_ENDPOINT")
    #     if not endpoint:
    #         raise ValueError("LOCAL_LLM_ENDPOINT environment variable is required for local_llm parser type.")
    #     return LocalLLMQueryParser(endpoint_url=endpoint)
    else:
        raise ValueError(f"Unsupported QUERY_PARSER_TYPE: {parser_type}")
