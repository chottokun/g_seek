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

    async def regenerate_query(self, original_query: str, topic: str, 
                               section_title: str, language: str) -> str:
        """
        Regenerates a search query when the original query yields no relevant results.
        
        Args:
            original_query: The query that failed to yield relevant results
            topic: The overall research topic
            section_title: The current section being researched
            language: Language for the prompt
        
        Returns:
            A new, potentially more effective search query
        """
        if language == "Japanese":
            prompt = f"""トピック: {topic}
セクション: {section_title}
元のクエリ: {original_query}

このクエリでは関連性の高い検索結果が見つかりませんでした。
より適切な検索クエリを生成してください。以下の点を考慮してください:
- より具体的なキーワードを使用
- 別の表現や類義語を試す
- 検索範囲を広げる（または狭める）

新しい検索クエリのみを出力してください（説明不要）。
"""
        else:
            prompt = f"""Topic: {topic}
Section: {section_title}
Original Query: {original_query}

This query did not yield any relevant search results.
Generate a more appropriate search query. Consider:
- Using more specific keywords
- Trying alternative expressions or synonyms
- Broadening (or narrowing) the search scope

Output only the new search query (no explanation needed).
"""
        
        logger.info(f"Regenerating query for: '{original_query}'")
        raw_query = await self.llm_client.generate_text(prompt=prompt)
        new_query = self._sanitize_query(raw_query)
        logger.info(f"Regenerated query: '{new_query}'")
        return new_query
