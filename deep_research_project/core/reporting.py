import logging
from typing import List
from deep_research_project.tools.llm_client import LLMClient
from deep_research_project.core.prompts import (
    FINAL_REPORT_PROMPT_JA, FINAL_REPORT_PROMPT_EN,
    NO_SOURCE_INFO_MSG_JA, NO_CITATION_INSTRUCTION_JA,
    NO_SOURCE_INFO_MSG_EN, NO_CITATION_INSTRUCTION_EN,
    SOURCE_INFO_PROMPT_JA, CITATION_INSTRUCTION_JA,
    SOURCE_INFO_PROMPT_EN, CITATION_INSTRUCTION_EN,
    MERMAID_DIAGRAM_PROMPT_JA, MERMAID_DIAGRAM_PROMPT_EN
)

logger = logging.getLogger(__name__)

class ResearchReporter:
    def __init__(self, llm_client: LLMClient):
        self.llm_client = llm_client

    async def finalize_report(self, topic: str, findings: List[str], sources: List[dict], language: str) -> str:
        """Synthesizes the final report from all completed sections."""
        logger.info("Synthesizing final report.")
        
        # Findings are already accumulated text summaries from the research loops
        full_context = "\n\n".join(findings)

        all_sources = []
        seen_links = set()
        for s in sources:
            # s might be a dict if coming from graph state
            link = s.get('link') if isinstance(s, dict) else s.link
            title = s.get('title') if isinstance(s, dict) else s.title
            
            if link and link not in seen_links:
                all_sources.append({"title": title, "link": link})
                seen_links.add(link)

        source_list_str = "\n".join([f"[{i+1}] {s['title']} ({s['link']})" for i, s in enumerate(all_sources)])

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

        from datetime import datetime
        current_date = datetime.now().strftime("%Y-%m-%d")

        if language == "Japanese":
            prompt = FINAL_REPORT_PROMPT_JA.format(
                topic=topic,
                current_date=current_date,
                full_context=full_context,
                source_info=source_info,
                citation_instruction=citation_instruction
            )
            mermaid_prompt = MERMAID_DIAGRAM_PROMPT_JA.format(topic=topic)
        else:
            prompt = FINAL_REPORT_PROMPT_EN.format(
                topic=topic,
                current_date=current_date,
                full_context=full_context,
                source_info=source_info,
                citation_instruction=citation_instruction
            )
            mermaid_prompt = MERMAID_DIAGRAM_PROMPT_EN.format(topic=topic)

        report = await self.llm_client.generate_text(prompt=prompt)
        
        # Safety cleanup: Remove any LLM-generated reference sections to prevent duplicates
        import re
        ref_patterns = [
            r"##?\s*(?:参考文献|References?|Sources?|出典(?::|：)?|情報源(?::|：)?).*",
            r"\d+\.\s+\[?参考文献\]?.*"
        ]
        for pattern in ref_patterns:
            report = re.split(pattern, report, flags=re.IGNORECASE | re.DOTALL)[0].strip()

        # Generate Mermaid diagram
        mermaid_full_prompt = f"--- CONTEXT ---\n{full_context}\n\n{mermaid_prompt}"
        mermaid_diagram = await self.llm_client.generate_text(prompt=mermaid_full_prompt)
        
        # Ensure code blocks for mermaid if LLM missed them
        if "```mermaid" not in mermaid_diagram and mermaid_diagram.strip().startswith(("graph", "erDiagram")):
            mermaid_diagram = f"```mermaid\n{mermaid_diagram.strip()}\n```"

        sources_footer = f"\n\n## Sources\n{source_list_str}" if source_list_str else ""
        
        final_output = f"{report}\n\n## Visual Summary\n{mermaid_diagram}{sources_footer}"
        return final_output
