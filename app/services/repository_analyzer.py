import json
import logging
from typing import Dict, List, Any

from groq import Groq
from app.config import GROQ_API_KEY

logger = logging.getLogger(__name__)

class RepositoryAnalyzer:
    """
    Uses an LLM to analyze a repository's metadata files (README, package.json, etc.)
    and outputs a structured JSON summary describing the architecture.
    """
    def __init__(self):
        self.groq_client = Groq(api_key=GROQ_API_KEY)
        self.model = "llama-3.1-8b-instant"

    def analyze(self, metadata_files: List[Dict[str, str]]) -> Dict[str, Any]:
        """
        Generates a structured JSON summary based on the given metadata files.
        If no files are provided, generates a default fallback summary.
        """
        if not metadata_files:
            logger.info("No metadata files found. Generating fallback summary.")
            return {
                "project_name": "Unknown",
                "project_type": "Unknown",
                "primary_language": "Unknown",
                "frameworks": [],
                "database": "Unknown",
                "main_modules": [],
                "architecture_summary": "No metadata files were found in the repository to generate an architecture summary."
            }

        # Concatenate file contents with a strict length limit to fit inside context window
        context = ""
        for f in metadata_files:
            path = f.get("path", "unknown")
            content = f.get("content", "")
            
            # Truncate extremely large files to prevent token overflow (approx 1000 lines max)
            if len(content) > 30000:
                content = content[:30000] + "\n...[TRUNCATED]"
                
            snippet = f"--- FILE: {path} ---\n{content}\n\n"
            context += snippet

        system_prompt = """You are an expert software architect. Analyze the provided repository metadata files (like README, package.json, requirements.txt, Dockerfiles, etc.).
Extract key architectural information and return ONLY a valid JSON object matching this exact schema:

{
  "project_name": "string",
  "project_type": "string (e.g. Web App, CLI, API, Library)",
  "primary_language": "string",
  "frameworks": ["list", "of", "strings"],
  "database": "string or None",
  "main_modules": ["list", "of", "strings"],
  "architecture_summary": "string (A clear 3-4 sentence summary of what this project does and how it is built)"
}

Do not include markdown code blocks around the JSON. Do not include any explanations. Return only valid parseable JSON."""

        try:
            logger.info("Sending metadata to Groq for Repository Intelligence Analysis...")
            response = self.groq_client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": context}
                ],
                max_tokens=1024,
                temperature=0.1,
                response_format={"type": "json_object"}
            )
            
            content = response.choices[0].message.content
            if not content:
                raise ValueError("LLM returned empty content")
                
            summary_json = json.loads(content)
            logger.info("Successfully generated repository summary JSON.")
            return summary_json

        except Exception as e:
            logger.error(f"Failed to generate repository summary: {e}")
            return {
                "project_name": "Error extracting project name",
                "project_type": "Unknown",
                "primary_language": "Unknown",
                "frameworks": [],
                "database": "Unknown",
                "main_modules": [],
                "architecture_summary": f"Failed to extract architecture summary: {str(e)}"
            }
