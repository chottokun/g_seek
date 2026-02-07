from typing import List, Dict, Optional, Callable
import logging
from deep_research_project.config.config import Configuration
from deep_research_project.tools.llm_client import LLMClient

logger = logging.getLogger(__name__)

class ReportGenerator:
    def __init__(self, llm_client: LLMClient, config: Configuration):
        self.llm_client = llm_client
        self.config = config

    async def finalize_report(self, topic: str, research_plan: List[Dict], language: str, progress_callback: Optional[Callable[[str], None]] = None) -> str:
        logger.info("Finalizing report with citations.")

        full_context = ""
        all_sources = []
        if research_plan:
            for i, sec in enumerate(research_plan):
                if sec['summary']:
                    full_context += f"\n\n### {sec['title']}\n{sec['summary']}"
                for s in sec['sources']:
                    if s['link'] not in [src['link'] for src in all_sources]:
                        all_sources.append(s)

        source_list_str = "\n".join([f"[{i+1}] {s['title']} ({s['link']})" for i, s in enumerate(all_sources)])

        if not source_list_str:
            source_info = "No specific web sources were found or selected for this research."
            citation_instruction = "Since no sources are available, do not use in-text citations."
        else:
            source_info = f"Reference Sources:\n{source_list_str}"
            if language == "Japanese":
                citation_instruction = "上記のソースに情報を帰属させるために、[1]や[2, 3]のような番号付きのインライン引用を必ず使用してください。"
            else:
                citation_instruction = "You MUST use numbered in-text citations such as [1] or [2, 3] to attribute information to the sources listed above."

        if language == "Japanese":
            prompt = (
                f"トピック: {topic} に関する最終的なリサーチレポートを統合してください。\n\n"
                f"リサーチコンテキスト（各セクションからの要約）:\n{full_context}\n\n"
                f"{source_info}\n\n"
                f"厳格な指示:\n"
                f"1. レポートは包括的でプロフェッショナルであり、明確な見出しを伴う構造になっている必要があります。出力は日本語で作成してください。\n"
                f"2. {citation_instruction}\n"
                f"3. ソースがある場合、すべての主要な主張やデータポイントには引用を付けることが理想的です。\n"
                f"4. 提供されたリストにないソースには言及しないでください。\n"
                f"5. 最後に調査結果のまとめを記述してください。"
            )
        else:
            prompt = (
                f"Synthesize a final research report for the topic: {topic}\n\n"
                f"Research Context (Summaries from various sections):\n{full_context}\n\n"
                f"{source_info}\n\n"
                f"STRICT INSTRUCTIONS:\n"
                f"1. The report must be comprehensive, professional, and well-structured with clear headings.\n"
                f"2. {citation_instruction}\n"
                f"3. Every major claim or data point should ideally be cited if sources are available.\n"
                f"4. Do not mention sources that are not in the provided list.\n"
                f"5. End with a summary of the findings."
            )

        if progress_callback: await progress_callback("Synthesizing final research report with all findings...")
        report = await self.llm_client.generate_text(prompt=prompt)

        sources_section = f"\n\n## Sources\n{source_list_str}" if source_list_str else ""
        final_report = f"{report}{sources_section}"
        if progress_callback: await progress_callback("Final report generation complete.")

        return final_report

    def format_follow_up_prompt(self, final_report: str, question: str, language: str) -> str:
        """Formats the prompt for a follow-up question based on the final report."""
        if language == "Japanese":
            return (
                f"以下のリサーチレポートに基づいて、ユーザーのフォローアップ質問に答えてください。\n\n"
                f"レポート:\n{final_report}\n\n"
                f"ユーザーの質問: {question}\n\n"
                f"レポートの内容のみに基づいて、明確で簡潔な回答を提供してください。回答は日本語で行ってください。"
            )
        else:
            return (
                f"Based on the following research report, answer the user's follow-up question.\n\n"
                f"Report:\n{final_report}\n\n"
                f"User Question: {question}\n\n"
                f"Provide a clear and concise answer based only on the report content."
            )
