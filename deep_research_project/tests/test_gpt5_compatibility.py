import unittest
import asyncio
from unittest.mock import patch, MagicMock, AsyncMock
from deep_research_project.config.config import Configuration
from deep_research_project.tools.llm_client import LLMClient

class TestGPT5Compatibility(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.mock_config = MagicMock(spec=Configuration)
        self.mock_config.LLM_PROVIDER = "openai"
        self.mock_config.LLM_TEMPERATURE = 0.7
        self.mock_config.LLM_MAX_TOKENS = 1000
        self.mock_config.OPENAI_API_KEY = "test"
        self.mock_config.OPENAI_API_BASE_URL = None
        self.mock_config.LLM_RATE_LIMIT_RPM = 0
        self.mock_config.ENABLE_CACHING = False

    async def test_gpt5_temperature_override_init(self):
        self.mock_config.LLM_MODEL = "gpt-5.2"
        with patch('langchain_openai.ChatOpenAI') as mock_chat:
            client = LLMClient(self.mock_config)
            mock_chat.assert_called_once()
            args, kwargs = mock_chat.call_args
            self.assertEqual(kwargs['temperature'], 1.0)

    async def test_gpt5_temperature_override_invoke(self):
        self.mock_config.LLM_MODEL = "gpt-5-preview"
        with patch('langchain_openai.ChatOpenAI') as mock_chat:
            mock_instance = mock_chat.return_value
            mock_instance.bind.return_value = mock_instance
            mock_instance.ainvoke = AsyncMock(return_value=MagicMock(content="response"))

            client = LLMClient(self.mock_config)
            await client.generate_text("test", temperature=0.5)

            # Check if bind was called with temperature=1.0 instead of 0.5
            mock_instance.bind.assert_called_with(temperature=1.0)

if __name__ == '__main__':
    unittest.main()
