import unittest
from unittest.mock import MagicMock, AsyncMock
from deep_research_project.core.planning import ResearchPlanner
from deep_research_project.config.config import Configuration
from deep_research_project.tools.llm_client import LLMClient

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

if __name__ == '__main__':
    unittest.main()
