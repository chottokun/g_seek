import logging
import json
import os
from datetime import datetime
from typing import Dict, List, Optional
from deep_research_project.tools.llm_client import LLMClient
from deep_research_project.core.prompts import (
    KI_METADATA_PROMPT_JA, KI_METADATA_PROMPT_EN
)

logger = logging.getLogger(__name__)

class KIDistiller:
    def __init__(self, llm_client: LLMClient, knowledge_root: str):
        self.llm_client = llm_client
        self.knowledge_root = knowledge_root
        os.makedirs(self.knowledge_root, exist_ok=True)

    async def distill_research(self, report: str, language: str) -> str:
        """Distills a research report into a structured Knowledge Item (KI)."""
        logger.info("Distilling research results into Knowledge Item.")
        
        # 1. Extract Metadata using LLM
        prompt = KI_METADATA_PROMPT_JA if language == "Japanese" else KI_METADATA_PROMPT_EN
        full_prompt = f"--- REPORT ---\n{report}\n\n{prompt}"
        
        metadata_raw = await self.llm_client.generate_text(prompt=full_prompt)
        
        # Simple JSON cleanup
        try:
            # Look for JSON block if LLM added formatting
            if "```json" in metadata_raw:
                metadata_raw = metadata_raw.split("```json")[1].split("```")[0].strip()
            elif "{" in metadata_raw:
                metadata_raw = metadata_raw[metadata_raw.find("{"):metadata_raw.rfind("}")+1].strip()
            
            metadata = json.loads(metadata_raw)
        except Exception as e:
            logger.error(f"Failed to parse KI metadata JSON: {e}. Raw: {metadata_raw}")
            # Fallback metadata
            metadata = {
                "title": "Untitled Research",
                "summary": "Full summary unavailable due to parsing error.",
                "keywords": [],
                "related_topics": []
            }

        # 2. Create the KI structure
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        ki_id = metadata.get("title", "research").lower().replace(" ", "_")[:50] + f"_{timestamp}"
        ki_path = os.path.join(self.knowledge_root, ki_id)
        os.makedirs(ki_path, exist_ok=True)
        os.makedirs(os.path.join(ki_path, "artifacts"), exist_ok=True)

        # 3. Save metadata.json
        ki_metadata = {
            "title": metadata.get("title"),
            "summary": metadata.get("summary"),
            "created_at": datetime.now().isoformat(),
            "keywords": metadata.get("keywords", []),
            "related_topics": metadata.get("related_topics", []),
            "references": ["Research Assistant Session"]
        }
        
        with open(os.path.join(ki_path, "metadata.json"), "w", encoding="utf-8") as f:
            json.dump(ki_metadata, f, ensure_ascii=False, indent=2)

        # 4. Save the research report as an artifact
        report_filename = "research_report.md"
        with open(os.path.join(ki_path, "artifacts", report_filename), "w", encoding="utf-8") as f:
            f.write(report)

        logger.info(f"Knowledge Item created at: {ki_path}")
        return ki_path
