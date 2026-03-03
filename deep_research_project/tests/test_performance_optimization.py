import asyncio
import unittest
import time
from unittest.mock import AsyncMock, patch
from deep_research_project.config.config import Configuration
from deep_research_project.core.execution import ResearchExecutor
from deep_research_project.tools.search_client import SearchResult

class TestPerformanceOptimization(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.config = Configuration()
        self.config.MAX_CONCURRENT_RETRIEVALS = 5
        self.config.BATCH_SIZE_RELEVANCE = 5
        self.config.ENABLE_CACHING = False # Disable for performance testing

        self.llm_client = AsyncMock()
        self.search_client = AsyncMock()
        self.content_retriever = AsyncMock()
        
        self.executor = ResearchExecutor(
            self.config, self.llm_client, self.search_client, self.content_retriever
        )

    async def test_parallel_retrieval_speed(self):
        # Setup 5 URLs, each taking 1s to retrieve
        results = [SearchResult(title=f"T{i}", link=f"L{i}", snippet=f"S{i}") for i in range(5)]
        
        async def mock_retrieve(url):
            await asyncio.sleep(1)
            return f"Content for {url}"
            
        self.content_retriever.retrieve_and_extract.side_effect = mock_retrieve
        
        start_time = time.time()
        await self.executor.retrieve_and_summarize(results, "query", "English")
        end_time = time.time()
        
        duration = end_time - start_time
        # In parallel, 5 URLs taking 1s each should take ~1s total (+ summarization overhead)
        # Without parallelization, it would take 5s.
        print(f"\nParallel Retrieval Duration: {duration:.2f}s")
        self.assertLess(duration, 2.0)

    async def test_batch_relevance_scoring_rpm(self):
        results = [SearchResult(title=f"T{i}", link=f"L{i}", snippet=f"S{i}") for i in range(10)]
        
        # Mock batch response
        from pydantic import BaseModel
        class ScoreBatch(BaseModel):
            scores: list[float]
        
        mock_batch_response = ScoreBatch(scores=[0.8] * 10)
        self.llm_client.generate_structured.return_value = mock_batch_response
        
        await self.executor.filter_by_relevance("query", results, "English")
        
        # 10 results, batch size 5 -> should result in 2 LLM calls
        # (Actually, my implementation scores them in chunks of 5)
        self.assertEqual(self.llm_client.generate_structured.call_count, 2)
        print(f"\nBatch Scoring LLM Calls: {self.llm_client.generate_structured.call_count}")

if __name__ == "__main__":
    unittest.main()
