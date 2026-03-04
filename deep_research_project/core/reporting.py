import logging
from typing import List
from deep_research_project.tools.llm_client import LLMClient
from deep_research_project.core.prompts import (
    FINAL_REPORT_PROMPT_JA, FINAL_REPORT_PROMPT_EN,
    CITATION_INSTRUCTION_JA, CITATION_INSTRUCTION_EN,
    NO_CITATION_INSTRUCTION_JA, NO_CITATION_INSTRUCTION_EN,
    SOURCE_INFO_PROMPT_JA, SOURCE_INFO_PROMPT_EN,
    NO_SOURCE_INFO_MSG_JA, NO_SOURCE_INFO_MSG_EN
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
            if language == "Japanese":
                source_info = NO_SOURCE_INFO_MSG_JA
                citation_instruction = NO_CITATION_INSTRUCTION_JA
            else:
                source_info = NO_SOURCE_INFO_MSG_EN
                citation_instruction = NO_CITATION_INSTRUCTION_EN
        else:
            if language == "Japanese":
                source_info = SOURCE_INFO_PROMPT_JA.format(source_list=source_list_str)
                citation_instruction = CITATION_INSTRUCTION_JA
            else:
                source_info = SOURCE_INFO_PROMPT_EN.format(source_list=source_list_str)
                citation_instruction = CITATION_INSTRUCTION_EN

        if language == "Japanese":
            prompt = FINAL_REPORT_PROMPT_JA.format(
                topic=topic,
                full_context=full_context,
                source_info=source_info,
                citation_instruction=citation_instruction
            )
        else:
            prompt = FINAL_REPORT_PROMPT_EN.format(
                topic=topic,
                full_context=full_context,
                source_info=source_info,
                citation_instruction=citation_instruction
            )

        report = await self.llm_client.generate_text(prompt=prompt)
        sources_footer = f"\n\n## Sources\n{source_list_str}" if source_list_str else ""
        return f"{report}{sources_footer}"
