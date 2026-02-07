import unittest
import asyncio
from unittest.mock import MagicMock, AsyncMock, patch
from deep_research_project.config.config import Configuration
from deep_research_project.core.research_loop import ResearchLoop
from deep_research_project.core.state import ResearchState

class TestKGExtractionError(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        # Mock configuration
        self.mock_config = MagicMock(spec=Configuration)
        self.mock_config.LLM_PROVIDER = "placeholder_llm"
        self.mock_config.SEARCH_API = "duckduckgo"
        self.mock_config.INTERACTIVE_MODE = False
        self.mock_config.MAX_RESEARCH_LOOPS = 2

        # Initialize state
        self.state = ResearchState(research_topic="Test Topic")
        self.state.language = "English"

        # Patch LLMClient and SearchClient
        self.llm_patcher = patch('deep_research_project.core.research_loop.LLMClient')
        self.search_patcher = patch('deep_research_project.core.research_loop.SearchClient')
        self.content_patcher = patch('deep_research_project.core.research_loop.ContentRetriever')

        self.mock_llm_cls = self.llm_patcher.start()
        self.mock_search_cls = self.search_patcher.start()
        self.mock_content_cls = self.content_patcher.start()

        self.mock_llm_client = self.mock_llm_cls.return_value
        self.mock_search_client = self.mock_search_cls.return_value
        self.mock_content_retriever = self.mock_content_cls.return_value

        # Mock progress callback
        self.mock_progress_callback = AsyncMock()

        # Initialize ResearchLoop
        self.loop = ResearchLoop(self.mock_config, self.state, progress_callback=self.mock_progress_callback)

    async def asyncTearDown(self):
        self.llm_patcher.stop()
        self.search_patcher.stop()
        self.content_patcher.stop()

    async def test_kg_extraction_handles_error(self):
        # Set up state with enough text to trigger extraction
        self.state.new_information = "This is a sufficiently long string for extraction to proceed."

        # Configure mock to raise an exception
        self.mock_llm_client.generate_structured = AsyncMock(side_effect=Exception("Simulated API Error"))

        # Call the method
        await self.loop._extract_entities_and_relations()

        # Verify that the exception was handled and progress callback was called
        self.mock_progress_callback.assert_called_with("Knowledge graph extraction skipped or failed.")

        # Verify that generate_structured was called
        self.mock_llm_client.generate_structured.assert_called_once()

        # Verify state is unchanged (empty KG)
        self.assertEqual(len(self.state.knowledge_graph_nodes), 0)
        self.assertEqual(len(self.state.knowledge_graph_edges), 0)

if __name__ == '__main__':
    unittest.main()
