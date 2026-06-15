import logging
from typing import List

from app.config import EMBEDDING_PROVIDER, OPENAI_API_KEY

logger = logging.getLogger(__name__)

# --- Module-level singleton for local model ---
_MODEL_NAME = "all-MiniLM-L6-v2"
_model_instance = None

def _get_local_model():
    global _model_instance
    if _model_instance is None:
        from sentence_transformers import SentenceTransformer
        logger.info(f"Loading SentenceTransformer model: {_MODEL_NAME}")
        _model_instance = SentenceTransformer(_MODEL_NAME)
        logger.info("Embedding model loaded and cached in memory.")
    return _model_instance

# --- Module-level singleton for OpenAI client ---
_openai_client = None

def _get_openai_client():
    global _openai_client
    if _openai_client is None:
        from openai import OpenAI
        logger.info("Initializing OpenAI client for embeddings...")
        _openai_client = OpenAI(api_key=OPENAI_API_KEY)
    return _openai_client

class CodeEmbedder:
    """
    Converts text/code into dense vectors.
    Supports local SentenceTransformer (default) or OpenAI embeddings (for low-memory deployments).
    """

    def __init__(self):
        self.provider = EMBEDDING_PROVIDER.lower()
        if self.provider == "openai":
            if not OPENAI_API_KEY:
                logger.warning("EMBEDDING_PROVIDER is 'openai' but OPENAI_API_KEY is missing!")
            self.client = _get_openai_client()
        else:
            # Trigger load at startup (warm-up)
            self.model = _get_local_model()

    def generate_embedding(self, text: str) -> List[float]:
        if not text or not text.strip():
            raise ValueError("Cannot generate embedding for an empty string.")
        
        try:
            if self.provider == "openai":
                response = self.client.embeddings.create(
                    model="text-embedding-3-small",
                    input=text.strip(),
                    dimensions=384  # Matches the dimension of all-MiniLM-L6-v2
                )
                return response.data[0].embedding
            else:
                return self.model.encode(text.strip(), normalize_embeddings=True).tolist()
        except Exception as e:
            logger.error(f"Embedding failed: {e}")
            raise RuntimeError(f"Failed to generate embedding: {e}")
