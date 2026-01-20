import asyncio
import unittest
from unittest.mock import MagicMock, AsyncMock, patch
from deep_research_project.config.config import Configuration
from deep_research_project.core.research_loop import ResearchLoop
from deep_research_project.core.state import ResearchState, SearchResult

class TestResearchLoopParallel(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.mock_config = MagicMock(spec=Configuration)
        self.mock_config.LLM_PROVIDER = "placeholder_llm"
        self.mock_config.MAX_SEARCH_RESULTS_PER_QUERY = 5
        self.mock_config.USE_SNIPPETS_ONLY_MODE = False
        self.mock_config.SUMMARIZATION_CHUNK_SIZE_CHARS = 1000
        self.mock_config.SUMMARIZATION_CHUNK_OVERLAP_CHARS = 100
        self.mock_config.MAX_RESEARCH_LOOPS = 1
        self.mock_config.LLM_MAX_RPM = 100
        self.mock_config.LLM_MAX_PARALLEL_REQUESTS = 10
        self.mock_config.INTERACTIVE_MODE = False
        self.mock_config.LANGUAGE = "English"
        self.mock_config.SEARCH_API = "duckduckgo"
        self.mock_config.PROCESS_PDF_FILES = True
        self.mock_config.MAX_TEXT_LENGTH_PER_SOURCE_CHARS = 0

        self.state = ResearchState("Test Topic")

        # Avoid initializing real clients that might fail or do IO
        with patch('deep_research_project.tools.llm_client.LLMClient.__init__', return_value=None):
            with patch('deep_research_project.tools.search_client.SearchClient.__init__', return_value=None):
                with patch('deep_research_project.tools.content_retriever.ContentRetriever.__init__', return_value=None):
                    self.loop = ResearchLoop(self.mock_config, self.state)
                    self.loop.llm_client = MagicMock()
                    self.loop.search_client = MagicMock()
                    self.loop.content_retriever = MagicMock()

    async def test_summarize_sources_parallel_fetching(self):
        # Prepare mock search results
        results = [
            SearchResult(title="Result 1", link="http://example.com/1", snippet="Snippet 1"),
            SearchResult(title="Result 2", link="http://example.com/2", snippet="Snippet 2"),
            SearchResult(title="Result 3", link="http://example.com/3", snippet="Snippet 3"),
        ]

        # Mock retrieval to be slow
        async def slow_retrieve(url):
            await asyncio.sleep(0.1)
            return f"Content for {url}"

        self.loop.content_retriever.retrieve_and_extract = AsyncMock(side_effect=slow_retrieve)

        # Mock LLM calls to avoid real ones
        self.loop.llm_client.generate_text = AsyncMock(return_value="Summary")
        self.loop.llm_client.generate_structured = AsyncMock()

        import time
        start_time = time.time()
        await self.loop._summarize_sources(results)
        end_time = time.time()

        duration = end_time - start_time
        print(f"Parallel fetch duration: {duration}")

        # Should be around 0.1s + some overhead, definitely < 0.25s
        self.assertLess(duration, 0.25, "Fetching should be parallel")
        self.assertEqual(self.loop.content_retriever.retrieve_and_extract.call_count, 3)

if __name__ == '__main__':
    unittest.main()
