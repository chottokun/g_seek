import unittest
import asyncio
import time
from unittest.mock import MagicMock, AsyncMock, patch
from deep_research_project.config.config import Configuration
from deep_research_project.tools.llm_client import LLMClient

class TestLLMClientRateLimit(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.mock_config = MagicMock(spec=Configuration)
        self.mock_config.LLM_PROVIDER = "openai"
        self.mock_config.LLM_MODEL = "gpt-4"
        self.mock_config.LLM_TEMPERATURE = 0.7
        self.mock_config.LLM_MAX_TOKENS = 1000
        self.mock_config.OPENAI_API_KEY = "test"
        self.mock_config.OPENAI_API_BASE_URL = None
        # 120 RPM means 1 request every 0.5 seconds
        self.mock_config.LLM_RATE_LIMIT_RPM = 120

    async def test_rate_limit_spacing(self):
        with patch('langchain_openai.ChatOpenAI'):
            client = LLMClient(self.mock_config)
            client.llm = AsyncMock()
            client.llm.ainvoke.return_value = MagicMock(content="response")

            start_time = asyncio.get_event_loop().time()
            # Send 12 requests. Burst capacity is 10.
            # Req 1-10: Instant
            # Req 11: 0.5s
            # Req 12: 1.0s
            tasks = [client.generate_text(f"p{i}") for i in range(12)]
            await asyncio.gather(*tasks)
            end_time = asyncio.get_event_loop().time()

            duration = end_time - start_time

            # With burst capacity 10 and 120 RPM (0.5s interval):
            # 12 requests should take approx 1.0s (wait for 11th and 12th).
            # Strict serialization would take (12-1)*0.5 = 5.5s.
            # No rate limit would take ~0s.

            self.assertGreaterEqual(duration, 1.0)
            self.assertLess(duration, 1.5)

    async def test_rate_limit_disabled(self):
        self.mock_config.LLM_RATE_LIMIT_RPM = 0
        with patch('langchain_openai.ChatOpenAI'):
            client = LLMClient(self.mock_config)
            client.llm = AsyncMock()
            client.llm.ainvoke.return_value = MagicMock(content="response")

            start_time = asyncio.get_event_loop().time()
            await asyncio.gather(
                client.generate_text("p1"),
                client.generate_text("p2"),
                client.generate_text("p3")
            )
            end_time = asyncio.get_event_loop().time()

            duration = end_time - start_time
            # Should be almost instantaneous
            self.assertLess(duration, 0.1)

if __name__ == '__main__':
    unittest.main()
