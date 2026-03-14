import logging
import re
from typing import List
from deep_research_project.tools.llm_client import LLMClient
from deep_research_project.core.state import VisualSummaryModel
from deep_research_project.core.prompts import (
    FINAL_REPORT_PROMPT_JA, FINAL_REPORT_PROMPT_EN,
    NO_SOURCE_INFO_MSG_JA, NO_CITATION_INSTRUCTION_JA,
    NO_SOURCE_INFO_MSG_EN, NO_CITATION_INSTRUCTION_EN,
    SOURCE_INFO_PROMPT_JA, CITATION_INSTRUCTION_JA,
    SOURCE_INFO_PROMPT_EN, CITATION_INSTRUCTION_EN,
    VISUAL_SUMMARY_PROMPT_JA, VISUAL_SUMMARY_PROMPT_EN
)

logger = logging.getLogger(__name__)

class ResearchReporter:
    def __init__(self, llm_client: LLMClient):
        self.llm_client = llm_client

    async def finalize_report(self, topic: str, findings: List[str], sources: List[dict], language: str) -> str:
        """Synthesizes the final report from all completed sections."""
        logger.info("Synthesizing final report.")
        
        # Findings are already accumulated text summaries from the research loops
        # We add section headers if findings are separate pieces to help the LLM structure the final report
        full_context = ""
        for i, f in enumerate(findings):
            full_context += f"\n\n--- SECTION {i+1} ---\n{f}"

        # Context length protection
        max_context_chars = getattr(self.llm_client.config, "MAX_FINAL_REPORT_CONTEXT_CHARS", 100000)
        if len(full_context) > max_context_chars:
            logger.warning(f"Full context ({len(full_context)} chars) exceeds safety limit ({max_context_chars}). Truncating.")
            full_context = full_context[:max_context_chars] + "\n\n[...一部の内容はコンテキストの制限により割愛されました / Some content truncated...]"

        all_sources = []
        seen_links = set()
        for s in sources:
            if not s:
                continue
            
            # Extract link and title reliably regardless of type
            if hasattr(s, 'link'):
                link = getattr(s, 'link')
                title = getattr(s, 'title', 'Unknown')
            elif isinstance(s, dict):
                link = s.get('link')
                title = s.get('title', 'Unknown')
            else:
                logger.warning(f"Unexpected source type: {type(s)}")
                continue
            
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
            visual_summary_prompt = VISUAL_SUMMARY_PROMPT_JA.format(topic=topic)
        else:
            prompt = FINAL_REPORT_PROMPT_EN.format(
                topic=topic,
                current_date=current_date,
                full_context=full_context,
                source_info=source_info,
                citation_instruction=citation_instruction
            )
            visual_summary_prompt = VISUAL_SUMMARY_PROMPT_EN.format(topic=topic)

        # We increase temperature slightly to allow for more creative synthesis of details
        report = await self.llm_client.generate_text(prompt=prompt, temperature=0.3)
        
        # Safety cleanup: Remove any LLM-generated reference sections to prevent duplicates
        # We only match if it looks like a header (starting with #) at the beginning of a line
        ref_patterns = [
            r"^##?\s*(?:参考文献|References?|Sources?|出典(?::|：)?|情報源(?::|：)?)\b",
            r"^\d+\.\s+\[?参考文献\]?\b"
        ]
        for pattern in ref_patterns:
            # Use MULTILINE flag to ensure ^ matches start of lines within the report
            # We don't use DOTALL here because we want to match the header line itself
            parts = re.split(pattern, report, flags=re.IGNORECASE | re.MULTILINE)
            if len(parts) > 1:
                report = parts[0].strip()

        # Generate structural visual summary (JSON)
        visual_full_prompt = f"--- CONTEXT ---\n{full_context}\n\n{visual_summary_prompt}"
        try:
            visual_model = await self.llm_client.generate_structured(prompt=visual_full_prompt, response_model=VisualSummaryModel)
            visual_data = visual_model.model_dump_json(by_alias=True, indent=2)
        except Exception as e:
            logger.warning(f"Structured visual summary failed: {e}. Falling back to text generation.")
            visual_data_raw = await self.llm_client.generate_text(prompt=visual_full_prompt)
            if "```json" in visual_data_raw:
                visual_data = visual_data_raw
            else:
                visual_data = f"```json\n{visual_data_raw.strip()}\n```"
        
        if not visual_data.strip().startswith("```"):
            visual_data = f"```json\n{visual_data}\n```"

        sources_footer = f"\n\n## Sources\n{source_list_str}" if source_list_str else ""
        
        final_output = f"{report}\n\n## Visual Summary\n{visual_data}{sources_footer}"
        return final_output
