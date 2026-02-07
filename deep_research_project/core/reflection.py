from typing import Optional, Callable, Tuple
import logging
from deep_research_project.config.config import Configuration
from deep_research_project.tools.llm_client import LLMClient

logger = logging.getLogger(__name__)

class ReflectionManager:
    def __init__(self, llm_client: LLMClient, config: Configuration):
        self.llm_client = llm_client
        self.config = config

    async def reflect_on_summary(self, topic: str, section_title: str, accumulated_summary: str, language: str, progress_callback: Optional[Callable[[str], None]] = None) -> Tuple[Optional[str], str]:
        if progress_callback: await progress_callback(f"Reflecting on findings for section: '{section_title}'...")
        if language == "Japanese":
            prompt = (
                f"トピック: {topic}\n"
                f"セクション: {section_title}\n"
                f"現在の要約:\n{accumulated_summary}\n\n"
                f"このセクションにさらなる調査が必要かどうかを評価してください。"
                f"フォーマット: EVALUATION: <CONTINUE|CONCLUDE>\nQUERY: <次の検索クエリまたは None>"
            )
        else:
            prompt = (
                f"Topic: {topic}\n"
                f"Section: {section_title}\n"
                f"Current Summary:\n{accumulated_summary}\n\n"
                f"Evaluate if more research is needed for this section. "
                f"Format: EVALUATION: <CONTINUE|CONCLUDE>\nQUERY: <Next search query or None>"
            )

        response = await self.llm_client.generate_text(prompt=prompt)
        # Simple parsing for reflection
        lines = response.split('\n')
        evaluation = "CONCLUDE"
        next_query = None
        for line in lines:
            if "EVALUATION:" in line.upper(): evaluation = line.split(":")[-1].strip().upper()
            if "QUERY:" in line.upper():
                q = line.split(":")[-1].strip()
                if q.lower() != "none": next_query = q

        return next_query, evaluation
