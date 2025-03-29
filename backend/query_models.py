from pydantic import BaseModel, Field
from typing import List, Dict, Optional, Literal

# Define possible sentiment/intent types
SentimentIntent = Literal[
    "positive",
    "negative",
    "neutral",
    "happiest", # For comparative positive
    "most_negative", # For comparative negative
    "objective", # For factual queries without sentiment focus
    "unclear" # If sentiment/intent cannot be determined
]

class ParsedQuery(BaseModel):
    """
    Represents the structured understanding of a user's natural language search query.
    """
    search_concepts: List[str] = Field(
        ...,
        description="Core concepts, topics, or keywords extracted from the query for semantic/text search."
    )
    sentiment_intent: SentimentIntent = Field(
        default="objective",
        description="The overall sentiment or intent expressed in the query (e.g., positive, negative, happiest)."
    )
    entities: Dict[str, List[str]] = Field(
        default_factory=dict,
        description="Named entities extracted from the query, categorized by type (e.g., {'PERSON': ['John Smith'], 'ORG': ['Tech Corp']})."
    )
    filters: Dict[str, List[str]] = Field(
        default_factory=dict,
        description="Metadata filters identified in the query (e.g., {'speakers': ['Jane Doe'], 'companies': ['Data Inc']})."
    )
    relationships: Optional[str] = Field(
        None,
        description="A description of relationships between concepts or entities mentioned (e.g., 'mentions X and Y', 'Company A about Topic B')."
    )
    original_query: str = Field(
        ...,
        description="The original, unmodified user query text."
    )

    class Config:
        # Example for documentation generation if needed
        json_schema_extra = { # Renamed from schema_extra for Pydantic v2 compatibility
            "example": {
                "search_concepts": ["Open RAN performance", "5G deployment"],
                "sentiment_intent": "positive",
                "entities": {"ORG": ["Telecom Corp"]},
                "filters": {"speakers": ["Dr. Alice Example"]},
                "relationships": "Telecom Corp positive statements about Open RAN",
                "original_query": "What positive things did Dr. Alice Example from Telecom Corp say about Open RAN performance and 5G deployment?"
            }
        }
