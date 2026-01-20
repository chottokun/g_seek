import asyncio
import time
import unittest
from unittest.mock import MagicMock, AsyncMock
from deep_research_project.config.config import Configuration
from deep_research_project.tools.llm_client import LLMClient

class TestLLMOptimization(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.mock_config = MagicMock(spec=Configuration)
        self.mock_config.LLM_PROVIDER = "openai"
        self.mock_config.LLM_MODEL = "gpt-4"
        self.mock_config.LLM_TEMPERATURE = 0.7
        self.mock_config.LLM_MAX_TOKENS = 1000
        self.mock_config.OPENAI_API_KEY = "test"
        self.mock_config.OPENAI_API_BASE_URL = None
        
        # Concurrency and Rate Limiting Settings
        self.mock_config.LLM_MAX_RPM = 10
        self.mock_config.LLM_MAX_PARALLEL_REQUESTS = 2
        
        # We need to mock ChatOpenAI to avoid import errors or API calls
        import sys
        sys.modules['langchain_openai'] = MagicMock()
        
        self.client = LLMClient(self.mock_config)
        self.client.llm = MagicMock()
        self.client.llm.ainvoke = AsyncMock(side_effect=lambda x: MagicMock(content=f"Response to {x}"))

    async def test_concurrency_limit(self):
        # We start 5 requests, but only 2 should run concurrently.
        # We can observe this by making ainvoke slow.
        async def slow_invoke(x):
            await asyncio.sleep(0.1)
            return MagicMock(content=f"Slow Response to {x}")
        
        self.client.llm.ainvoke.side_effect = slow_invoke
        
        start_time = time.time()
        tasks = [self.client.generate_text(f"Prompt {i}") for i in range(4)]
        await asyncio.gather(*tasks)
        end_time = time.time()
        
        # 4 requests, parallel=2, delay=0.1s each.
        # Batch 1 (2 requests): 0.1s
        # Batch 2 (2 requests): 0.1s
        # Total ~0.2s
        self.assertGreaterEqual(end_time - start_time, 0.2)
        self.assertLess(end_time - start_time, 0.3)

    async def test_rpm_limit(self):
        # Set RPM to 2
        self.client.max_rpm = 2
        self.client.request_times = []
        
        self.client.llm.ainvoke.side_effect = lambda x: MagicMock(content=f"Fast Response")
        
        start_time = time.time()
        # First 2 requests should be instant
        await self.client.generate_text("P1")
        await self.client.generate_text("P2")
        
        # Third request should trigger wait (coarse check)
        # In our implementation, it waits for the first request to be 60s old.
        # For testing, we can manually manipulate request_times
        self.client.request_times = [time.time() - 59.8, time.time() - 59.8]
        
        await self.client.generate_text("P3")
        end_time = time.time()
        
        # Should have waited ~0.2s
        self.assertGreaterEqual(end_time - start_time, 0.1)

if __name__ == '__main__':
    unittest.main()
