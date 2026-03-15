import unittest
from unittest.mock import MagicMock, AsyncMock, patch
from datetime import datetime
from deep_research_project.core.reporting import ResearchReporter
from deep_research_project.core.state import Source, VisualSummaryModel, VisualSummaryNode, VisualSummaryEdge
from deep_research_project.tools.llm_client import LLMClient

class TestResearchReporter(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.mock_llm_client = MagicMock(spec=LLMClient)
        self.mock_llm_client.config = MagicMock()
        # Set a small limit for truncation tests
        self.mock_llm_client.config.MAX_FINAL_REPORT_CONTEXT_CHARS = 100
        self.reporter = ResearchReporter(self.mock_llm_client)

    async def test_finalize_report_english_happy_path(self):
        topic = "AI Trends"
        findings = ["AI is evolving.", "Generative AI is popular."]
        sources = [
            {"title": "Source 1", "link": "http://example.com/1"},
            Source(title="Source 2", link="http://example.com/2")
        ]
        language = "English"

        self.mock_llm_client.generate_text = AsyncMock(side_effect=[
            "This is the final report body.", # First call for report
            "```json\n{\"nodes\": [], \"edges\": []}\n```" # Fallback call if needed, but we'll mock structured
        ])

        mock_visual_model = VisualSummaryModel(nodes=[], edges=[])
        self.mock_llm_client.generate_structured = AsyncMock(return_value=mock_visual_model)

        report = await self.reporter.finalize_report(topic, findings, sources, language)

        self.assertIn("This is the final report body.", report)
        self.assertIn("## Visual Summary", report)
        self.assertIn("## Sources", report)
        self.assertIn("[1] Source 1 (http://example.com/1)", report)
        self.assertIn("[2] Source 2 (http://example.com/2)", report)

        # Verify prompt content (English)
        prompt = self.mock_llm_client.generate_text.call_args_list[0].kwargs['prompt']
        self.assertIn(topic, prompt)
        self.assertIn("AI is evolving.", prompt)
        self.assertIn("Source 1", prompt)

    async def test_finalize_report_japanese_happy_path(self):
        topic = "AIの動向"
        findings = ["AIは進化しています。", "生成AIが人気です。"]
        sources = [{"title": "情報源1", "link": "http://example.com/1"}]
        language = "Japanese"

        self.mock_llm_client.generate_text = AsyncMock(return_value="これは最終レポートです。")
        self.mock_llm_client.generate_structured = AsyncMock(return_value=VisualSummaryModel(nodes=[], edges=[]))

        report = await self.reporter.finalize_report(topic, findings, sources, language)

        self.assertIn("これは最終レポートです。", report)
        self.assertIn("## Sources", report)

        # Verify prompt content (Japanese)
        prompt = self.mock_llm_client.generate_text.call_args_list[0].kwargs['prompt']
        self.assertIn("トピック: 'AIの動向'", prompt)

    async def test_finalize_report_truncation(self):
        self.mock_llm_client.config.MAX_FINAL_REPORT_CONTEXT_CHARS = 50
        findings = ["This is a very long finding that exceeds fifty characters."]

        self.mock_llm_client.generate_text = AsyncMock(return_value="Report")
        self.mock_llm_client.generate_structured = AsyncMock(return_value=VisualSummaryModel(nodes=[], edges=[]))

        await self.reporter.finalize_report("Topic", findings, [], "English")

        prompt = self.mock_llm_client.generate_text.call_args_list[0].kwargs['prompt']
        # The first 50 chars of context includes the section header (approx 20 chars) and some finding content
        self.assertIn("This is a very long ", prompt)
        self.assertIn("Some content truncated", prompt)

    async def test_finalize_report_source_deduplication(self):
        sources = [
            {"title": "S1", "link": "http://dup.com"},
            {"title": "S2", "link": "http://dup.com"}, # Duplicate link
            {"title": "S3", "link": "http://unique.com"}
        ]
        self.mock_llm_client.generate_text = AsyncMock(return_value="Report")
        self.mock_llm_client.generate_structured = AsyncMock(return_value=VisualSummaryModel(nodes=[], edges=[]))

        report = await self.reporter.finalize_report("Topic", [], sources, "English")

        self.assertIn("[1] S1 (http://dup.com)", report)
        self.assertIn("[2] S3 (http://unique.com)", report)
        self.assertNotIn("S2", report)

    async def test_finalize_report_reference_stripping(self):
        # The LLM mistakenly includes a References section
        llm_response = "Report body.\n\n## References\n[1] Source\n[2] Other"
        self.mock_llm_client.generate_text = AsyncMock(return_value=llm_response)
        self.mock_llm_client.generate_structured = AsyncMock(return_value=VisualSummaryModel(nodes=[], edges=[]))

        report = await self.reporter.finalize_report("Topic", [], [], "English")

        # Should contain "Report body." but not the LLM's "## References"
        self.assertIn("Report body.", report)
        self.assertNotIn("## References", report)

    async def test_finalize_report_reference_stripping_japanese(self):
        # Test Japanese reference headers
        llm_response = "レポート本文。\n\n## 参考文献\n[1] 出典"
        self.mock_llm_client.generate_text = AsyncMock(return_value=llm_response)
        self.mock_llm_client.generate_structured = AsyncMock(return_value=VisualSummaryModel(nodes=[], edges=[]))

        report = await self.reporter.finalize_report("トピック", [], [], "Japanese")

        self.assertIn("レポート本文。", report)
        self.assertNotIn("## 参考文献", report)

    async def test_finalize_report_reference_stripping_numbered(self):
        # Test numbered reference headers
        llm_response = "Report body.\n\n1. [参考文献]\n[1] Source"
        self.mock_llm_client.generate_text = AsyncMock(return_value=llm_response)
        self.mock_llm_client.generate_structured = AsyncMock(return_value=VisualSummaryModel(nodes=[], edges=[]))

        report = await self.reporter.finalize_report("Topic", [], [], "English")

        self.assertIn("Report body.", report)
        self.assertNotIn("1. [参考文献]", report)

    async def test_finalize_report_visual_summary_fallback(self):
        self.mock_llm_client.generate_text = AsyncMock(side_effect=[
            "Report", # Call 1: Report
            "{\"nodes\": [{\"id\": \"1\", \"label\": \"Fallback\"}], \"edges\": []}" # Call 2: Fallback text
        ])
        # Fail the structured call
        self.mock_llm_client.generate_structured = AsyncMock(side_effect=Exception("Structured failed"))

        report = await self.reporter.finalize_report("Topic", [], [], "English")

        self.assertIn("## Visual Summary", report)
        self.assertIn("Fallback", report)
        self.assertIn("```json\n{\"nodes\": [{\"id\": \"1\", \"label\": \"Fallback\"}], \"edges\": []}\n```", report) # Fallback wraps in ```json

    async def test_finalize_report_visual_summary_no_wrapping_initially(self):
        # Test when generate_structured returns a JSON string without wrapping (happens in the fallback logic)
        self.mock_llm_client.generate_text = AsyncMock(return_value="Report")

        mock_visual_model = VisualSummaryModel(nodes=[], edges=[])
        # mock_visual_model.model_dump_json() returns raw JSON
        self.mock_llm_client.generate_structured = AsyncMock(return_value=mock_visual_model)

        report = await self.reporter.finalize_report("Topic", [], [], "English")

        self.assertIn("```json\n{\n  \"nodes\": [],\n  \"edges\": []\n}\n```", report)

    async def test_finalize_report_no_sources(self):
        self.mock_llm_client.generate_text = AsyncMock(return_value="Report")
        self.mock_llm_client.generate_structured = AsyncMock(return_value=VisualSummaryModel(nodes=[], edges=[]))

        report = await self.reporter.finalize_report("Topic", [], [], "English")

        self.assertNotIn("## Sources", report)
        prompt = self.mock_llm_client.generate_text.call_args_list[0].kwargs['prompt']
        self.assertIn("No source information available", prompt)

    async def test_finalize_report_malformed_sources(self):
        # Test handling of unexpected source types
        sources = [
            None,
            "not a dict or object",
            {"title": "Valid"}, # Missing link
            {"link": "http://valid.com", "title": "Valid"},
            {"link": "http://valid.com"} # Duplicate link, will be ignored but good to test title fallback
        ]
        self.mock_llm_client.generate_text = AsyncMock(return_value="Report")
        self.mock_llm_client.generate_structured = AsyncMock(return_value=VisualSummaryModel(nodes=[], edges=[]))

        report = await self.reporter.finalize_report("Topic", [], sources, "English")

        # Only the one with link should be present
        self.assertIn("[1] Valid (http://valid.com)", report)
        # Verify it doesn't crash on None or string

    async def test_finalize_report_empty_findings(self):
        self.mock_llm_client.generate_text = AsyncMock(return_value="Report")
        self.mock_llm_client.generate_structured = AsyncMock(return_value=VisualSummaryModel(nodes=[], edges=[]))

        report = await self.reporter.finalize_report("Topic", [], [], "English")

        self.assertIn("Report", report)
        prompt = self.mock_llm_client.generate_text.call_args_list[0].kwargs['prompt']
        # full_context should be empty string
        self.assertIn("--- CONTEXT START ---\n\n--- CONTEXT END ---", prompt)

if __name__ == "__main__":
    unittest.main()
