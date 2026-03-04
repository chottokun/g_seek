import logging
from typing import List
from deep_research_project.tools.llm_client import LLMClient
from deep_research_project.core.prompts import (
    FINALIZE_REPORT_PROMPT_JA, FINALIZE_REPORT_PROMPT_EN,
    CITATION_INSTRUCTION_JA, CITATION_INSTRUCTION_EN, CITATION_NONE_INSTRUCTION
)

logger = logging.getLogger(__name__)

class ResearchReporter:
    def __init__(self, llm_client: LLMClient):
        self.llm_client = llm_client

    async def finalize_report(self, topic: str, research_plan: List[dict], language: str) -> str:
        """Synthesizes the final report from all completed sections."""
        logger.info("Synthesizing final report.")
        
        full_context = ""
        all_sources = []
        seen_links = set()
        for sec in research_plan:
            if sec['summary']:
                full_context += f"\n\n### {sec['title']}\n{sec['summary']}"
            for s in sec['sources']:
                if s.link not in seen_links:
                    all_sources.append(s)
                    seen_links.add(s.link)

        source_list_str = "\n".join([f"[{i+1}] {s.title} ({s.link})" for i, s in enumerate(all_sources)])

        if not source_list_str:
            source_info = "No web sources were found."
            citation_instruction = CITATION_NONE_INSTRUCTION
        else:
            source_info = f"Reference Sources:\n{source_list_str}"
            if language == "Japanese":
                citation_instruction = CITATION_INSTRUCTION_JA
            else:
                citation_instruction = CITATION_INSTRUCTION_EN

        if language == "Japanese":
            prompt = FINALIZE_REPORT_PROMPT_JA.format(
                topic=topic,
                full_context=full_context,
                source_info=source_info,
                citation_instruction=citation_instruction
            )
        else:
            prompt = FINALIZE_REPORT_PROMPT_EN.format(
                topic=topic,
                full_context=full_context,
                source_info=source_info,
                citation_instruction=citation_instruction
            )

        report = await self.llm_client.generate_text(prompt=prompt)
        sources_footer = f"\n\n## Sources\n{source_list_str}" if source_list_str else ""
        return f"{report}{sources_footer}"
