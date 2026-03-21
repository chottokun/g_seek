import unittest
from unittest.mock import MagicMock, AsyncMock
from deep_research_project.core.planning import ResearchPlanner
from deep_research_project.config.config import Configuration
from deep_research_project.tools.llm_client import LLMClient
from deep_research_project.core.state import ResearchPlanModel, Section

class TestResearchPlanner(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.mock_config = MagicMock(spec=Configuration)
        self.mock_llm = MagicMock(spec=LLMClient)
        self.planner = ResearchPlanner(self.mock_config, self.mock_llm)

    def test_sanitize_query(self):
        # Test empty input
        self.assertEqual(self.planner._sanitize_query(""), "")
        self.assertEqual(self.planner._sanitize_query(None), "")

        # Test markdown removal
        self.assertEqual(self.planner._sanitize_query("**Bold** `Code` \"Quote\""), "Bold Code Quote")
        self.assertEqual(self.planner._sanitize_query("__Italic__"), "Italic")

        # Test multi-line input (should take only first line)
        self.assertEqual(self.planner._sanitize_query("Line 1\nLine 2"), "Line 1")

        # Test truncation at word boundary
        long_query = "This is a very long query that exceeds one hundred characters and should be truncated at a word boundary eventually."
        sanitized = self.planner._sanitize_query(long_query)
        self.assertLessEqual(len(sanitized), 100)
        self.assertTrue(sanitized.startswith("This is a very long query"))
        # Check it's not cut in the middle of a word if possible
        self.assertEqual(sanitized, "This is a very long query that exceeds one hundred characters and should be truncated at a word")

        # Test truncation without spaces (should just cut)
        long_query_no_spaces = "A" * 110
        sanitized_no_spaces = self.planner._sanitize_query(long_query_no_spaces)
        self.assertEqual(len(sanitized_no_spaces), 100)

    async def test_generate_initial_query_sanitization(self):
        self.mock_llm.generate_text = AsyncMock(return_value="**Bold Query**\nWith multiple lines")

        query = await self.planner.generate_initial_query("Topic", "Title", "Desc", "English")

        # Should be sanitized (no bold, only first line)
        self.assertEqual(query, "Bold Query")

    async def test_regenerate_query_sanitization(self):
        self.mock_llm.generate_text = AsyncMock(return_value="`Code Query`\nMore lines")

        query = await self.planner.regenerate_query("Old Query", "Topic", "Title", "English")

        # Should be sanitized (no code fences, only first line)
        self.assertEqual(query, "Code Query")

    async def test_generate_plan_success_en(self):
        # Setup mock data
        mock_sections = [
            Section(title="Section 1", description="Description 1"),
            Section(title="Section 2", description="Description 2")
        ]
        mock_plan = ResearchPlanModel(sections=mock_sections)
        self.mock_llm.generate_structured = AsyncMock(return_value=mock_plan)
        self.mock_config.RESEARCH_PLAN_MIN_SECTIONS = 3
        self.mock_config.RESEARCH_PLAN_MAX_SECTIONS = 5

        progress_callback = AsyncMock()

        topic = "AI Trends"
        language = "English"

        # Execute
        plan = await self.planner.generate_plan(topic, language, progress_callback)

        # Verify
        self.assertEqual(len(plan), 2)
        self.assertEqual(plan[0]["title"], "Section 1")
        self.assertEqual(plan[0]["status"], "pending")
        progress_callback.assert_called_with("Generating structured research plan...")

        # Verify LLM call
        args, _ = self.mock_llm.generate_structured.call_args
        prompt = args[0]
        self.assertIn(topic, prompt)
        self.assertIn("at least 3", prompt)
        self.assertIn("at most 5", prompt)

    async def test_generate_plan_success_ja(self):
        # Setup mock data
        mock_sections = [
            Section(title="セクション1", description="説明1")
        ]
        mock_plan = ResearchPlanModel(sections=mock_sections)
        self.mock_llm.generate_structured = AsyncMock(return_value=mock_plan)

        topic = "AIの動向"
        language = "Japanese"

        # Execute
        plan = await self.planner.generate_plan(topic, language)

        # Verify
        self.assertEqual(len(plan), 1)
        self.assertEqual(plan[0]["title"], "セクション1")

        # Verify LLM call
        args, _ = self.mock_llm.generate_structured.call_args
        prompt = args[0]
        self.assertIn(topic, prompt)
        self.assertIn("プランは少なくとも", prompt)

    async def test_generate_plan_fallback(self):
        # Setup mock to raise exception
        self.mock_llm.generate_structured = AsyncMock(side_effect=Exception("LLM failure"))

        topic = "Failure Topic"

        # Execute
        plan = await self.planner.generate_plan(topic, "English")

        # Verify fallback plan
        self.assertEqual(len(plan), 1)
        self.assertEqual(plan[0]["title"], "General Research")
        self.assertIn(topic, plan[0]["description"])
        self.assertEqual(plan[0]["status"], "pending")

if __name__ == '__main__':
    unittest.main()
