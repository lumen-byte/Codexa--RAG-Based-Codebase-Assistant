import logging
from typing import List

from fastapi import APIRouter, HTTPException, Depends
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.auth.dependencies import get_current_user
from app.db.database import get_db
from app.db.models import RepositorySummary, User

from app.rag.chain import RAGChain

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/rag", tags=["RAG Query"])


class AskRequest(BaseModel):
    question: str = Field(..., min_length=3, description="The question to ask the codebase assistant.")
    repo_url: str | None = Field(None, description="Optional repository URL to inject architecture context.")
    ingestion_progress: int | None = Field(None, description="Current ingestion progress percentage (0-100).")


class Citation(BaseModel):
    file_path: str
    start_line: int
    end_line: int


class AskResponse(BaseModel):
    answer: str
    citations: List[Citation]


# Lazy singleton — RAGChain is created only on the FIRST request, not at server startup.
# This prevents the Qdrant + embedding model from loading into memory during boot,
# which was causing Uvicorn worker processes to crash on Render's 512MB free tier.
_rag_chain: RAGChain | None = None

def _get_rag_chain() -> RAGChain | None:
    global _rag_chain
    if _rag_chain is None:
        try:
            logger.info("Lazily initializing RAGChain on first request...")
            _rag_chain = RAGChain()
            logger.info("RAGChain initialized successfully.")
        except Exception as e:
            logger.error(f"CRITICAL: Failed to initialize RAGChain: {e}")
            return None
    return _rag_chain


def _format_question(question: str, progress: int | None) -> str:
    """Prepend a warning to the LLM if the ingestion is incomplete."""
    if progress is not None and progress < 100:
        warning = f"System Note: The repository is currently only {progress}% ingested. If you cannot find the full answer, please mention to the user that the ingestion is incomplete, but try to answer based on what you have.\n\n"
        return warning + question
    return question


@router.post("/ask", response_model=AskResponse, status_code=200)
def ask_question(
    request: AskRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> AskResponse:
    """Non-streaming endpoint — returns full answer + citations."""
    rag_chain = _get_rag_chain()
    if not rag_chain:
        raise HTTPException(status_code=503, detail="RAG service unavailable.")
        
    repo_summary = None
    if request.repo_url:
        summary = db.query(RepositorySummary).filter(RepositorySummary.repo_url == request.repo_url).first()
        if summary:
            repo_summary = summary.summary_json

    final_question = _format_question(request.question, request.ingestion_progress)

    try:
        result = rag_chain.ask_question(question=final_question, repo_url=request.repo_url, repo_summary=repo_summary)
        return AskResponse(
            answer=result.get("answer", "No answer could be generated."),
            citations=result.get("citations", []),
        )
    except ValueError as ve:
        raise HTTPException(status_code=400, detail=str(ve))
    except RuntimeError as re:
        logger.error(f"Runtime error during RAG query: {re}")
        raise HTTPException(status_code=502, detail=str(re))
    except Exception as e:
        logger.error(f"Unexpected error: {e}")
        raise HTTPException(status_code=500, detail="Internal server error.")


@router.post("/ask/stream")
def ask_question_stream(
    request: AskRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Streaming SSE endpoint — yields tokens in real-time as Groq generates them.
    Frontend connects and receives words immediately instead of waiting.
    """
    rag_chain = _get_rag_chain()
    if not rag_chain:
        raise HTTPException(status_code=503, detail="RAG service unavailable.")
        
    repo_summary = None
    if request.repo_url:
        summary = db.query(RepositorySummary).filter(RepositorySummary.repo_url == request.repo_url).first()
        if summary:
            repo_summary = summary.summary_json

    final_question = _format_question(request.question, request.ingestion_progress)

    return StreamingResponse(
        rag_chain.stream_question(question=final_question, repo_url=request.repo_url, repo_summary=repo_summary),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )
