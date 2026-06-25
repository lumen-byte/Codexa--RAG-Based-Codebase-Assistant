import logging
import time
import json
from typing import Any, Dict, Generator

from groq import Groq

from app.ingestion.embedder import CodeEmbedder
from app.retrieval.vector_store import VectorDBClient
from app.rag.query_analyzer import QueryAnalyzer
from app.config import GROQ_API_KEY, GROQ_MODEL, LLM_PROVIDER

logger = logging.getLogger(__name__)

MAX_CONTEXT_CHARS = 4000


class RAGChain:
    """
    RAG pipeline using Groq cloud inference for fast, free LLM responses.
    Groq runs Llama 3.1 8B at 200+ tokens/sec — ~100x faster than local CPU.
    """

    def __init__(self):
        self.embedder = CodeEmbedder()
        self.db_client = VectorDBClient()
        self.query_analyzer = QueryAnalyzer()
        self.groq_client = Groq(api_key=GROQ_API_KEY)
        logger.info(f"RAGChain ready. Using Groq model: {GROQ_MODEL}")

    def _retrieve(self, question: str, repo_url: str | None = None, repo_summary: dict | None = None) -> tuple[str | None, list, dict, str]:
        """Embed the question and retrieve top relevant code chunks."""
        t_start = time.perf_counter()
        
        # Intent Detection Phase
        target_modules = None
        intent = "unknown"
        if repo_summary:
            main_modules = repo_summary.get("main_modules", [])
            if main_modules:
                analysis = self.query_analyzer.detect_intent(question, main_modules)
                target_modules = analysis.get("selected_modules", [])
                intent = analysis.get("intent", "unknown")
        
        # Vector Generation Phase
        t_embed_start = time.perf_counter()
        vector = self.embedder.generate_embedding(question)
        t_embed = time.perf_counter() - t_embed_start
        
        # Database Retrieval Phase
        t_db_start = time.perf_counter()
        results = self.db_client.search_similar(query_embedding=vector, top_k=10, target_modules=target_modules, repo_url=repo_url)
        t_db = time.perf_counter() - t_db_start
        
        metrics: Dict[str, Any] = {
            "embedding_time": t_embed,
            "retrieval_time": t_db
        }

        if not results:
            return None, [], metrics, intent

        # Confidence Scoring
        try:
            max_score = max((float(r.get("score") or 0) for r in results), default=0.0)
            confidence = "High" if max_score > 0.25 else "Low"
        except Exception:
            confidence = "Low"
        metrics["confidence"] = confidence

        # Boosting and Deduplication
        boosted_results = []
        for r in results:
            score = r.get("score", 0)
            p = r["payload"]
            fp = p.get("file_path", "").lower()
            if "readme" in fp or "main.py" in fp or "config.py" in fp:
                score += 0.1
            r["score"] = score
            boosted_results.append(r)
            
        boosted_results.sort(key=lambda x: x["score"], reverse=True)
        
        # Sort by file and line for merging
        sorted_for_merge = sorted(boosted_results, key=lambda x: (x["payload"].get("file_path", ""), x["payload"].get("start_line", 0)))
        
        merged_chunks = []
        if sorted_for_merge:
            current = sorted_for_merge[0]["payload"].copy()
            current_score = sorted_for_merge[0]["score"]
            for i in range(1, len(sorted_for_merge)):
                p = sorted_for_merge[i]["payload"]
                if p.get("file_path") == current.get("file_path") and p.get("start_line", 0) <= current.get("end_line", 0) + 10:
                    current["end_line"] = max(current.get("end_line", 0), p.get("end_line", 0))
                    current["content"] += "\n" + p.get("content", "")
                    current_score = max(current_score, sorted_for_merge[i]["score"])
                else:
                    merged_chunks.append({"score": current_score, "payload": current})
                    current = p.copy()
                    current_score = sorted_for_merge[i]["score"]
            merged_chunks.append({"score": current_score, "payload": current})

        merged_chunks.sort(key=lambda x: x["score"], reverse=True)

        context, citations = "", []
        seen_files = set()
        seen_chunks = set()

        for i, r in enumerate(merged_chunks):
            p = r["payload"]
            file_path = p.get("file_path", "unknown")
            content = p.get("content", "")
            s, e = p.get("start_line", 0), p.get("end_line", 0)
            chunk_type = p.get("chunk_type", "chunk")
            name = p.get("name", "Unknown")

            if len(content) > 800:
                content = content[:800] + "\n...[truncated]"

            chunk_id = f"{file_path}_{s}_{e}"
            if chunk_id in seen_chunks:
                continue
            seen_chunks.add(chunk_id)

            snippet = f"[{i+1}] File: {file_path} | Type: {chunk_type} | Name: {name} | Lines: {s}-{e}\n{content}\n\n"
            if len(context) + len(snippet) > MAX_CONTEXT_CHARS:
                break
            context += snippet
            
            # Keep frontend citations deduplicated by file to avoid UI clutter
            if file_path not in seen_files:
                citations.append({"file_path": file_path, "start_line": s, "end_line": e})
                seen_files.add(file_path)

        # Inject confidence context directly into snippet top
        context = f"RETRIEVAL CONFIDENCE: {confidence}\n\n" + context

        return context, citations, metrics, intent

    def _messages(self, question: str, context: str, repo_summary: dict | None = None, intent: str = "unknown") -> Any:
        """Build the chat messages list for the Groq API."""
        
        system_content = (
            "You are an expert, repository-aware AI Codebase Assistant (similar to GitHub Copilot Chat, Cursor, or Sourcegraph Cody).\n\n"
            "CRITICAL RULES:\n"
            "1. IDENTIFY BEFORE ANSWERING: Always start by silently identifying the Tech Stack, Framework, Entry Point, and Key Modules based on the repository context.\n"
            "2. UNCERTAIN LANGUAGE FORBIDDEN: Never use phrases like 'likely', 'probably', 'may be', 'possibly', 'appears to', or 'seems to' unless RETRIEVAL CONFIDENCE is 'Low'. If confidence is high and evidence exists, answer authoritatively.\n"
            "3. EXPLAIN WHY: Do not just list technologies. Explain WHY they exist (e.g. 'FastAPI: Purpose: async backend. Why: type safety, speed').\n"
            "4. Answer ONLY using the retrieved repository context. Never hallucinate code.\n"
            "5. Never generate generic explanations if repository information exists. Prefer explaining the actual implementation over theory.\n"
            "6. Mention actual files, modules, classes, functions, and technologies used in this repository.\n"
            "7. Never say 'AI model' (you are powered by Gemini or Groq depending on the deployment).\n"
            "8. Never say 'database' generically if PostgreSQL or Qdrant is known to be used.\n"
            "9. Always use professional developer Markdown formatting. Use nested bullets, callout boxes (like > [!NOTE]), horizontal rules, and numbered steps.\n"
            "10. When returning code, use fenced Markdown with the language specified. Immediately follow the code block with a breakdown of: Purpose, Inputs, Outputs, Execution Flow, Dependencies, and Time Complexity (if applicable).\n"
            "11. If RETRIEVAL CONFIDENCE is 'Low', explicitly state: 'Repository evidence is insufficient.'\n"
            "\n"
            "CITATION RULES:\n"
            "Always end your answer with a Citations section, sorted by relevance and deduplicated:\n"
            "## Sources\n"
            "📄 [file_path]\n"
            "Function: [Name]\n"
            "Lines: [start_line]–[end_line]\n"
            "Why this file is relevant: [Reason]\n\n"
        )
        
        # Inject structural templates based on intent
        if intent == "repository_overview":
            system_content += (
                "You are providing a Repository Overview. Structure your response EXACTLY as follows:\n"
                "# Repository Overview\n"
                "## Purpose\n"
                "## Tech Stack\n"
                "## Architecture\n"
                "## Execution Flow\n"
                "## Important Modules\n"
                "## Design Decisions\n"
                "## Scalability\n"
                "## Performance Optimizations\n"
            )
        elif intent == "architecture":
            system_content += (
                "You are explaining Architecture. Structure your response EXACTLY as follows:\n"
                "# Architecture\n"
                "## Visual Flow\n"
                "(Create a text-based ASCII flow diagram representing the architecture flow here)\n"
                "## Components\n"
                "## Execution Flow\n"
                "## Technologies Used\n"
                "## Design Decisions\n"
                "## Advantages\n"
            )
        elif intent == "code_explanation":
            system_content += (
                "You are explaining Code. Structure your response EXACTLY as follows:\n"
                "# Code Explanation\n"
                "## File\n"
                "## Function/Class\n"
                "## Purpose\n"
                "## Logic\n"
                "## Dependencies\n"
                "## Complexity\n"
            )
        elif intent == "interview_questions":
            system_content += (
                "You are providing Interview Questions. Structure your response EXACTLY as follows:\n"
                "# Interview Question\n"
                "## Why Interviewers Ask It\n"
                "## Ideal Answer\n"
                "## Follow-up Questions\n"
                "## Relevant Files\n"
            )
        elif intent == "bug_analysis":
            system_content += (
                "You are analyzing a Bug. Structure your response EXACTLY as follows:\n"
                "# Bug Analysis\n"
                "## Problem\n"
                "## Root Cause\n"
                "## Relevant Files\n"
                "## Suggested Fix\n"
            )
        elif intent == "review_repository":
            system_content += (
                "You are providing a Developer Review. Structure your response EXACTLY as follows:\n"
                "# Developer Review\n"
                "## Architecture\n"
                "## Strengths\n"
                "## Weaknesses\n"
                "## Scalability\n"
                "## Security\n"
                "## Performance\n"
                "## Code Quality\n"
                "## Maintainability\n"
                "## Suggested Improvements\n"
                "## Production Readiness Score\n"
            )
        else:
            system_content += "Structure your response with clear Markdown headings (e.g. # Explanation, ## Details).\n"
        
        if repo_summary:
            architecture = repo_summary.get("architecture_summary", "Unknown architecture")
            project_type = repo_summary.get("project_type", "Unknown type")
            language = repo_summary.get("primary_language", "Unknown language")
            frameworks = ", ".join(repo_summary.get("frameworks", []))
            
            files_indexed = repo_summary.get("total_files", "Unknown")
            chunks_indexed = repo_summary.get("total_chunks", "Unknown")
            
            system_content += (
                f"\n\n--- GLOBAL REPOSITORY CONTEXT ---\n"
                f"Project Type: {project_type}\n"
                f"Primary Language: {language}\n"
                f"Frameworks: {frameworks}\n"
                f"Architecture Summary: {architecture}\n"
                f"Files Indexed: {files_indexed}\n"
                f"Chunks Indexed: {chunks_indexed}\n"
                f"---------------------------------\n"
            )

        return [
            {
                "role": "system",
                "content": system_content,
            },
            {
                "role": "user",
                "content": f"RETRIEVED CODE CHUNKS:\n{context}\n\nUSER QUESTION:\n{question}",
            },
        ]

    def ask_question(self, question: str, repo_url: str | None = None, repo_summary: dict | None = None) -> Dict[str, Any]:
        """Non-streaming: returns full answer + citations with accurate metrics."""
        t_start = time.perf_counter()
        
        context, citations, metrics, intent = self._retrieve(question, repo_url, repo_summary)

        if context is None:
            return {
                "answer": "No relevant code found. Please ingest a repository first.",
                "citations": [],
            }

        t_prompt_start = time.perf_counter()
        messages = self._messages(question, context, repo_summary, intent)
        t_prompt = time.perf_counter() - t_prompt_start

        t_llm_start = time.perf_counter()
        try:
            response = self.groq_client.chat.completions.create(
                model=GROQ_MODEL,
                messages=messages,
                max_tokens=512,
                temperature=0.2,
            )
            content = response.choices[0].message.content
            answer = str(content).strip() if content else ""
        except Exception as e:
            logger.error(f"Groq API generation failed: {e}")
            answer = "Error generating response: Groq API is currently unavailable or returned an error. Please try again later."
            
        t_llm = time.perf_counter() - t_llm_start
        t_total = time.perf_counter() - t_start
        
        logger.info(
            f"RAG Metrics -> Total: {t_total:.2f}s | "
            f"Embed: {metrics['embedding_time']:.2f}s | "
            f"Search: {metrics['retrieval_time']:.2f}s | "
            f"Prompt: {t_prompt:.3f}s | "
            f"LLM: {t_llm:.2f}s"
        )
        
        return {"answer": answer, "citations": citations}

    def stream_question(self, question: str, repo_url: str | None = None, repo_summary: dict | None = None) -> Generator[str, None, None]:
        """
        SSE streaming via Groq. First token arrives in ~0.3-0.5s.
        Yields: 'data: {"token":"..."}\n\n' per token
                'data: {"citations":[...],"done":true}\n\n' at end
        """
        context, citations, metrics, intent = self._retrieve(question, repo_url, repo_summary)

        if context is None:
            yield f'data: {json.dumps({"token": "No relevant code found. Please ingest a repository first."})}\n\n'
            yield f'data: {json.dumps({"citations": [], "done": True})}\n\n'
            return

        try:
            stream = self.groq_client.chat.completions.create(
                model=GROQ_MODEL,
                messages=self._messages(question, context, repo_summary, intent),
                max_tokens=512,
                temperature=0.2,
                stream=True,
            )

            for chunk in stream:
                if chunk.choices and chunk.choices[0].delta.content:
                    token = chunk.choices[0].delta.content
                    yield f'data: {json.dumps({"token": token})}\n\n'

        except Exception as e:
            logger.error(f"Groq streaming error: {e}")
            yield f'data: {json.dumps({"token": f"Error: {str(e)}"})}\n\n'

        yield f'data: {json.dumps({"citations": citations, "done": True})}\n\n'
