import unittest
import asyncio
from unittest.mock import patch, MagicMock, AsyncMock

from deep_research_project.config.config import Configuration
from deep_research_project.core.research_loop import ResearchLoop
from deep_research_project.core.state import ResearchState, ResearchPlanModel, Section

class TestInterruption(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.mock_config = MagicMock(spec=Configuration)
        self.mock_config.INTERACTIVE_MODE = False
        self.mock_config.MAX_RESEARCH_LOOPS = 2
        self.mock_config.RESEARCH_PLAN_MIN_SECTIONS = 3
        self.mock_config.RESEARCH_PLAN_MAX_SECTIONS = 5
        self.mock_config.MAX_CONCURRENT_CHUNKS = 5
        self.mock_config.MAX_SEARCH_RESULTS_PER_QUERY = 3
        self.mock_config.USE_SNIPPETS_ONLY_MODE = False
        self.mock_config.SUMMARIZATION_CHUNK_SIZE_CHARS = 1000
        self.mock_config.SUMMARIZATION_CHUNK_OVERLAP_CHARS = 100
        self.mock_config.MAX_QUERY_WORDS = 10

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

    async def test_run_loop_interruption(self):
        # Mock structured plan
        mock_plan = ResearchPlanModel(sections=[
            Section(title="Sec 1", description="Desc 1"),
            Section(title="Sec 2", description="Desc 2")
        ])
        self.mock_llm_client.generate_structured = AsyncMock(return_value=mock_plan)
        self.mock_llm_client.generate_text = AsyncMock(return_value="Test Result")

        # Start the loop but it should see is_interrupted immediately
        self.state.is_interrupted = True

        await self.loop.run_loop()

        # It should have called _generate_research_plan (since state.research_plan was empty)
        # but then broken out of the while loop.
        self.assertEqual(self.state.current_section_index, 0)
        # Final report should still be generated (with whatever was there)
        self.assertIsNotNone(self.state.final_report)

if __name__ == '__main__':
    unittest.main()
