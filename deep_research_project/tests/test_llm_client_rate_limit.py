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
            # Send 3 requests
            await asyncio.gather(
                client.generate_text("p1"),
                client.generate_text("p2"),
                client.generate_text("p3")
            )
            end_time = asyncio.get_event_loop().time()

            duration = end_time - start_time
            # Request 1: 0s
            # Request 2: 0.5s
            # Request 3: 1.0s
            # Total duration should be at least 1.0s
            self.assertGreaterEqual(duration, 1.0)
            self.assertLess(duration, 1.5) # Should not be too much more

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
