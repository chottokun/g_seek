import logging
from typing import Optional, List, Callable
from deep_research_project.config.config import Configuration
from deep_research_project.tools.llm_client import LLMClient
from deep_research_project.core.state import ResearchPlanModel, Section
from deep_research_project.core.prompts import (
    RESEARCH_PLAN_PROMPT_JA, RESEARCH_PLAN_PROMPT_EN,
    INITIAL_QUERY_PROMPT_JA, INITIAL_QUERY_PROMPT_EN
)

logger = logging.getLogger(__name__)

class ResearchPlanner:
    def __init__(self, config: Configuration, llm_client: LLMClient):
        self.config = config
        self.llm_client = llm_client

    async def generate_plan(self, topic: str, language: str, 
                            progress_callback: Optional[Callable] = None) -> List[dict]:
        """Generates a structured research plan."""
        logger.info(f"Generating research plan for topic: {topic}")
        if progress_callback: await progress_callback("Generating structured research plan...")
        
        if language == "Japanese":
            prompt = RESEARCH_PLAN_PROMPT_JA.format(
                topic=topic,
                min_sections=self.config.RESEARCH_PLAN_MIN_SECTIONS,
                max_sections=self.config.RESEARCH_PLAN_MAX_SECTIONS
            )
        else:
            prompt = RESEARCH_PLAN_PROMPT_EN.format(
                topic=topic,
                min_sections=self.config.RESEARCH_PLAN_MIN_SECTIONS,
                max_sections=self.config.RESEARCH_PLAN_MAX_SECTIONS
            )

        try:
            plan_model = await self.llm_client.generate_structured(prompt, ResearchPlanModel)
            # Convert Pydantic model to the list of dictionaries expected by ResearchState
            return [
                {
                    "title": sec.title,
                    "description": sec.description,
                    "status": "pending",
                    "summary": "",
                    "sources": []
                } for sec in plan_model.sections
            ]
        except Exception as e:
            logger.error(f"Failed to generate research plan: {e}. Using fallback.")
            return [{
                "title": "General Research",
                "description": f"Comprehensive research on {topic}",
                "status": "pending",
                "summary": "",
                "sources": []
            }]

    async def generate_initial_query(self, topic: str, language: str,
                                     progress_callback: Optional[Callable] = None) -> str:
        """Generates the first search query to start research."""
        if language == "Japanese":
            prompt = INITIAL_QUERY_PROMPT_JA.format(topic=topic)
        else:
            prompt = INITIAL_QUERY_PROMPT_EN.format(topic=topic)
            
        logger.info("Generating initial query.")
        if progress_callback: await progress_callback("Generating initial search query...")
        
        raw_query = await self.llm_client.generate_text(prompt=prompt)
        return self._sanitize_query(raw_query)

    def _sanitize_query(self, query: str) -> str:
        """Cleans and truncates the query to prevent API errors."""
        if not query: return ""
        # Remove markdown bold/italic/code fences
        clean = query.strip().replace("**", "").replace("__", "").replace("`", "").replace('"', '')
        # Take only the first line if multiple lines returned
        clean = clean.split('\n')[0].strip()
        # Truncate to a reasonable character length (e.g., 100 characters)
        if len(clean) > 100:
            clean = clean[:100].rsplit(' ', 1)[0] # Try to cut at word boundary
        return clean
