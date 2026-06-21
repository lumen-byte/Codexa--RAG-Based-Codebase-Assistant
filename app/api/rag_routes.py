import logging
from typing import List

from fastapi import APIRouter, HTTPException, Depends
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.db.models import RepositorySummary

from app.rag.chain import RAGChain

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/rag", tags=["RAG Query"])


class AskRequest(BaseModel):
    question: str = Field(..., min_length=3, description="The question to ask the codebase assistant.")
    repo_url: str | None = Field(None, description="Optional repository URL to inject architecture context.")


class Citation(BaseModel):
    file_path: str
    start_line: int
    end_line: int


class AskResponse(BaseModel):
    answer: str
    citations: List[Citation]


# Singleton — keeps the embedding model loaded in memory across requests
try:
    rag_chain = RAGChain()
except Exception as e:
    logger.error(f"CRITICAL: Failed to initialize RAGChain on startup: {e}")
    rag_chain = None


@router.post("/ask", response_model=AskResponse, status_code=200)
def ask_question(request: AskRequest, db: Session = Depends(get_db)) -> AskResponse:
    """Non-streaming endpoint — returns full answer + citations."""
    if not rag_chain:
        raise HTTPException(status_code=503, detail="RAG service unavailable.")
        
    repo_summary = None
    if request.repo_url:
        summary = db.query(RepositorySummary).filter(RepositorySummary.repo_url == request.repo_url).first()
        if summary:
            repo_summary = summary.summary_json

    try:
        result = rag_chain.ask_question(question=request.question, repo_summary=repo_summary)
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
def ask_question_stream(request: AskRequest, db: Session = Depends(get_db)):
    """
    Streaming SSE endpoint — yields tokens in real-time as Ollama generates them.
    Frontend connects and receives words immediately instead of waiting.
    """
    if not rag_chain:
        raise HTTPException(status_code=503, detail="RAG service unavailable.")
        
    repo_summary = None
    if request.repo_url:
        summary = db.query(RepositorySummary).filter(RepositorySummary.repo_url == request.repo_url).first()
        if summary:
            repo_summary = summary.summary_json

    return StreamingResponse(
        rag_chain.stream_question(question=request.question, repo_summary=repo_summary),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )
