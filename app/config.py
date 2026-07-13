from dotenv import load_dotenv
import os

load_dotenv()


DATABASE_URL = os.getenv("DATABASE_URL")


CLERK_SECRET_KEY = os.getenv("CLERK_SECRET_KEY", "").strip()
FRONTEND_URL = os.getenv("FRONTEND_URL", "http://localhost:3000,http://localhost:3001,http://127.0.0.1:3000,http://127.0.0.1:3001,https://codexarag.vercel.app").strip()


GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")
MAX_FILES_TO_INDEX = int(os.getenv("MAX_FILES_TO_INDEX", "200"))


QDRANT_HOST = os.getenv("QDRANT_HOST", "localhost").strip()
QDRANT_PORT = int(os.getenv("QDRANT_PORT", "6333"))
QDRANT_URL = os.getenv("QDRANT_URL", "").strip()
QDRANT_API_KEY = os.getenv("QDRANT_API_KEY", "").strip()


OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "llama3.2:1b")


LLM_PROVIDER = os.getenv("LLM_PROVIDER", "groq")  # 'groq' or 'ollama'


GROQ_API_KEY = os.getenv("GROQ_API_KEY", "").strip()
GROQ_MODEL = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile").strip()


EMBEDDING_PROVIDER = os.getenv("EMBEDDING_PROVIDER", "local").strip()  # 'local', 'openai', or 'gemini'
EMBEDDING_BATCH_SIZE = int(os.getenv("EMBEDDING_BATCH_SIZE", "100"))
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "").strip()
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "").strip()