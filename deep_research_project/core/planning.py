from typing import List, Optional, Callable
import logging
from deep_research_project.config.config import Configuration
from deep_research_project.core.state import ResearchPlanModel
from deep_research_project.tools.llm_client import LLMClient

logger = logging.getLogger(__name__)

class PlanGenerator:
    def __init__(self, llm_client: LLMClient, config: Configuration):
        self.llm_client = llm_client
        self.config = config

    async def generate_plan(self, topic: str, language: str, progress_callback: Optional[Callable[[str], None]] = None) -> List[dict]:
        logger.info(f"Generating research plan for topic: {topic} (Language: {language})")
        if progress_callback: await progress_callback("Generating structured research plan...")

        try:
            min_sec = getattr(self.config, "RESEARCH_PLAN_MIN_SECTIONS", 3)
            max_sec = getattr(self.config, "RESEARCH_PLAN_MAX_SECTIONS", 5)
            if language == "Japanese":
                prompt = (
                    f"以下のリサーチトピックに基づいて、{min_sec}〜{max_sec}つの主要なセクションで構成される構造化されたリサーチ計画を生成してください。\n"
                    f"リサーチトピック: {topic}\n\n"
                    f"各セクションについて、タイトルとリサーチすべき内容の簡潔な説明を提供してください。"
                )
            else:
                prompt = (
                    f"Based on the following research topic, generate a structured research plan consisting of {min_sec} to {max_sec} key sections.\n"
                    f"Research Topic: {topic}\n\n"
                    f"For each section, provide a title and a brief description of what should be researched."
                )

            plan_model = await self.llm_client.generate_structured(prompt=prompt, response_model=ResearchPlanModel)

            research_plan = []
            for sec in plan_model.sections:
                research_plan.append({
                    "title": sec.title,
                    "description": sec.description,
                    "status": "pending",
                    "summary": "",
                    "sources": []
                })

            # Visibility Enhancement: Emit plan details as formatted message
            plan_str = "## 📋 Research Plan\n\n"
            for i, sec in enumerate(research_plan):
                plan_str += f"{i+1}. **{sec['title']}**\n   - {sec['description']}\n\n"
            if progress_callback:
                await progress_callback(plan_str)

            logger.info(f"Research plan generated with {len(research_plan)} sections.")
            return research_plan

        except Exception as e:
            logger.error(f"Error generating research plan: {e}", exc_info=True)
            # Return a default plan in case of failure
            return [{"title": "General Research", "description": f"Research on {topic}", "status": "pending", "summary": "", "sources": []}]
