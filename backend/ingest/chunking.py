import tiktoken
from langchain.text_splitter import RecursiveCharacterTextSplitter
from typing import List
import logging

logger = logging.getLogger(__name__)

# --- Tokenizer Function ---
# Using tiktoken for potentially better alignment with embedding models
# Choose an appropriate encoding name, e.g., 'cl100k_base' for many newer models
# or 'p50k_base' for older ones. Check your embedding model's recommendation.
# For paraphrase-MiniLM-L3-v2, a simple word count *might* suffice, but tiktoken is more robust.
_ENCODING_NAME = "cl100k_base" # Default, adjust if needed
try:
    _TOKENIZER = tiktoken.get_encoding(_ENCODING_NAME)
except Exception:
    logger.warning(f"Could not get tiktoken encoding '{_ENCODING_NAME}'. Falling back to 'p50k_base'.")
    _ENCODING_NAME = "p50k_base" # Fallback
    try:
        _TOKENIZER = tiktoken.get_encoding(_ENCODING_NAME)
    except Exception as e:
         logger.error(f"Failed to initialize tiktoken tokenizer: {e}. Chunk size will be based on characters.")
         _TOKENIZER = None

def _tiktoken_len(text: str) -> int:
    """Returns the number of tokens in a text string using tiktoken."""
    if _TOKENIZER is None:
        # Fallback to character count if tokenizer failed
        return len(text)
    return len(_TOKENIZER.encode(text))

# --- Chunking Function ---

def chunk_text(
    text: str,
    chunk_size: int = 256, # Target chunk size in tokens
    chunk_overlap: int = 50 # Overlap size in tokens
) -> List[str]:
    """
    Splits text into chunks using a recursive strategy based on token count.

    Args:
        text: The input text to chunk.
        chunk_size: The target maximum size of each chunk (in tokens).
        chunk_overlap: The desired overlap between consecutive chunks (in tokens).

    Returns:
        A list of text chunks.
    """
    if not text:
        return []

    # Define the separators for recursive splitting
    # Prioritize larger semantic units first
    separators = ["\n\n", "\n", ". ", "? ", "! ", " ", ""]

    # Initialize the splitter
    # If tiktoken failed, length_function defaults to len (character count)
    length_func = _tiktoken_len if _TOKENIZER else len
    unit = "tokens" if _TOKENIZER else "characters"
    logger.debug(f"Initializing RecursiveCharacterTextSplitter with chunk_size={chunk_size} {unit}, chunk_overlap={chunk_overlap} {unit}")

    text_splitter = RecursiveCharacterTextSplitter(
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
        length_function=length_func,
        separators=separators,
        add_start_index=False, # We don't need start index from splitter
        is_separator_regex=False,
    )

    try:
        chunks = text_splitter.split_text(text)
        # Filter out any potential empty chunks that might occur
        chunks = [chunk for chunk in chunks if chunk.strip()]
        logger.info(f"Split text into {len(chunks)} chunks (target size: {chunk_size} {unit}, overlap: {chunk_overlap} {unit}).")
        return chunks
    except Exception as e:
        logger.error(f"Error during text chunking: {e}", exc_info=True)
        # Fallback: return the original text as a single chunk if splitting fails
        return [text]

# --- Example Usage (for testing) ---
if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO)
    sample_text = """
This is the first paragraph. It contains several sentences. We want to split this text effectively.

This is the second paragraph. It discusses a different topic. Recursive splitting should handle this break. It might also be long enough to be split further based on sentences. What happens with questions? Or exclamations!

This is a third, shorter paragraph.

And a final sentence.
"""
    chunks = chunk_text(sample_text, chunk_size=30, chunk_overlap=5) # Small size for demo
    print(f"\n--- Sample Text Chunked (Size: 30, Overlap: 5) ---")
    for i, chunk in enumerate(chunks):
        print(f"Chunk {i+1} (Length: {_tiktoken_len(chunk)} tokens):")
        print(f"'{chunk}'")
        print("-" * 10)

    long_text = " ".join(["word"] * 500)
    chunks_long = chunk_text(long_text, chunk_size=100, chunk_overlap=20)
    print(f"\n--- Long Text Chunked (Size: 100, Overlap: 20) ---")
    print(f"Number of chunks: {len(chunks_long)}")
    if chunks_long:
        print(f"First chunk length: {_tiktoken_len(chunks_long[0])} tokens")
        print(f"Second chunk length: {_tiktoken_len(chunks_long[1])} tokens" if len(chunks_long) > 1 else "")
        print(f"First chunk preview: '{chunks_long[0][:100]}...'")
