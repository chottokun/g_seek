import unittest
from unittest.mock import patch, MagicMock, AsyncMock
from deep_research_project.config.config import Configuration
from deep_research_project.core.research_loop import ResearchLoop
from deep_research_project.core.state import ResearchState, ResearchPlanModel, Section

class TestResearchLoopErrorHandling(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        # Mock Configuration
        self.mock_config = MagicMock(spec=Configuration)
        self.mock_config.LLM_PROVIDER = "placeholder_llm"
        self.mock_config.SEARCH_API = "duckduckgo"
        self.mock_config.INTERACTIVE_MODE = False
        self.mock_config.MAX_RESEARCH_LOOPS = 2
        self.mock_config.RESEARCH_PLAN_MIN_SECTIONS = 3
        self.mock_config.RESEARCH_PLAN_MAX_SECTIONS = 5
        self.mock_config.MAX_SEARCH_RESULTS_PER_QUERY = 3
        self.mock_config.USE_SNIPPETS_ONLY_MODE = False
        self.mock_config.SUMMARIZATION_CHUNK_SIZE_CHARS = 1000
        self.mock_config.SUMMARIZATION_CHUNK_OVERLAP_CHARS = 100
        self.mock_config.LOG_LEVEL = "INFO"
        self.mock_config.MAX_CONCURRENT_CHUNKS = 5
        self.mock_config.LLM_RATE_LIMIT_RPM = 60

        self.state = ResearchState(research_topic="Test Topic")

        # Patch clients
        self.llm_patcher = patch('deep_research_project.core.research_loop.LLMClient')
        self.search_patcher = patch('deep_research_project.core.research_loop.SearchClient')
        self.content_patcher = patch('deep_research_project.core.research_loop.ContentRetriever')

        self.mock_llm_client = self.llm_patcher.start().return_value
        self.mock_search_client = self.search_patcher.start().return_value
        self.mock_content_retriever = self.content_patcher.start().return_value

        self.loop = ResearchLoop(self.mock_config, self.state)

    async def asyncTearDown(self):
        self.llm_patcher.stop()
        self.search_patcher.stop()
        self.content_patcher.stop()

    async def test_generate_research_plan_failure_fallback(self):
        """Test that research plan generation falls back to a default plan on error."""
        # Arrange
        self.mock_llm_client.generate_structured.side_effect = Exception("LLM Failure")

        # Act
        await self.loop._generate_research_plan()

        # Assert
        # Should have 1 fallback section
        self.assertEqual(len(self.loop.state.research_plan), 1)
        self.assertEqual(self.loop.state.research_plan[0]['title'], "General Research")
        self.assertIn("Test Topic", self.loop.state.research_plan[0]['description'])
        self.assertEqual(self.loop.state.current_section_index, -1)
