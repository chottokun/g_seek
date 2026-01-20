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
        # We start 4 requests, but only 2 should run concurrently.
        async def slow_invoke(x):
            await asyncio.sleep(0.1)
            return MagicMock(content=f"Slow Response to {x}")
        
        self.client.llm.ainvoke.side_effect = slow_invoke
        
        start_time = time.time()
        tasks = [self.client.generate_text(f"Prompt {i}") for i in range(4)]
        await asyncio.gather(*tasks)
        end_time = time.time()
        
        duration = end_time - start_time
        self.assertGreaterEqual(duration, 0.18)
        self.assertLess(duration, 0.35)

    async def test_rpm_limit(self):
        self.client.max_rpm = 2
        self.client.request_times = []
        
        self.client.llm.ainvoke.side_effect = lambda x: MagicMock(content=f"Fast Response")
        
        start_time = time.time()
        await self.client.generate_text("P1")
        await self.client.generate_text("P2")
        
        self.client.request_times = [time.time() - 59.85, time.time() - 59.85]
        
        await self.client.generate_text("P3")
        end_time = time.time()
        
        self.assertGreaterEqual(end_time - start_time, 0.1)

    async def test_rpm_limit_burst_fast(self):
        # Set RPM to 5
        self.client.max_rpm = 5
        self.client.request_times = []

        self.client.llm.ainvoke.side_effect = lambda x: MagicMock(content=f"Fast Response")

        now = time.time()
        # 4 slots taken, will expire in 0.1s
        self.client.request_times = [now - 59.9] * 4

        # Start 2 requests. 1st should fill the 5th slot, 2nd should wait 0.1s.
        tasks = [self.client.generate_text(f"Burst {i}") for i in range(2)]

        start_time = time.time()
        await asyncio.gather(*tasks)
        end_time = time.time()

        self.assertGreaterEqual(end_time - start_time, 0.08)
        self.assertLess(end_time - start_time, 0.5)

    async def test_semaphore_release_on_error(self):
        self.client.llm.ainvoke.side_effect = Exception("LLM Error")

        with self.assertRaises(Exception):
            await self.client.generate_text("Fail")

        self.assertEqual(self.client.semaphore._value, self.mock_config.LLM_MAX_PARALLEL_REQUESTS)

if __name__ == '__main__':
    unittest.main()
