import logging
from typing import List
from deep_research_project.tools.llm_client import LLMClient

logger = logging.getLogger(__name__)

class ResearchReporter:
    def __init__(self, llm_client: LLMClient):
        self.llm_client = llm_client

    async def finalize_report(self, topic: str, research_plan: List[dict], language: str) -> str:
        """Synthesizes the final report from all completed sections."""
        logger.info("Synthesizing final report.")
        
        full_context = ""
        all_sources = []
        for sec in research_plan:
            if sec['summary']:
                full_context += f"\n\n### {sec['title']}\n{sec['summary']}"
            for s in sec['sources']:
                if s.link not in [src.link for src in all_sources]:
                    all_sources.append(s)

        source_list_str = "\n".join([f"[{i+1}] {s.title} ({s.link})" for i, s in enumerate(all_sources)])

        if not source_list_str:
            source_info = "No web sources were found."
            citation_instruction = "Do not use citations."
        else:
            source_info = f"Reference Sources:\n{source_list_str}"
            if language == "Japanese":
                citation_instruction = "番号付きのインライン引用 [1] を使用して出典を明記してください。"
            else:
                citation_instruction = "Use numbered in-text citations like [1] to attribute information."

        if language == "Japanese":
            prompt = (
                f"トピック: {topic} に関する最終リサーチレポートを作成してください。\n\n"
                f"コンテキスト:\n{full_context}\n\n"
                f"{source_info}\n\n"
                f"指示: 包括的で専門的な構成（日本語）にしてください。{citation_instruction}"
            )
        else:
            prompt = (
                f"Synthesize a final report for: {topic}\n\n"
                f"Context:\n{full_context}\n\n"
                f"{source_info}\n\n"
                f"Instruction: Professional structure. {citation_instruction}"
            )

        report = await self.llm_client.generate_text(prompt=prompt)
        sources_footer = f"\n\n## Sources\n{source_list_str}" if source_list_str else ""
        return f"{report}{sources_footer}"
