import unittest
import asyncio
from unittest.mock import MagicMock, AsyncMock, patch
from deep_research_project.tools.llm_client import LLMClient, LLMPolicyError
from deep_research_project.config.config import Configuration
from pydantic import BaseModel

class MockModel(BaseModel):
    items: list[str]

class TestLLMPolicyResilience(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.mock_config = MagicMock(spec=Configuration)
        self.mock_config.LLM_PROVIDER = "openai"
        self.mock_config.LLM_MODEL = "gpt-4"
        self.mock_config.LLM_TEMPERATURE = 0.7
        self.mock_config.LLM_MAX_TOKENS = 1000
        self.mock_config.OPENAI_API_KEY = "test"
        self.mock_config.OPENAI_API_BASE_URL = None
        self.mock_config.LLM_RATE_LIMIT_RPM = 0
        self.mock_config.ENABLE_CACHING = False

        with patch('langchain_openai.ChatOpenAI'):
            self.client = LLMClient(self.mock_config)

    async def test_generate_text_policy_error(self):
        # Mock ainvoke to raise a policy error
        self.client.llm = AsyncMock()
        self.client.llm.ainvoke.side_effect = Exception("This request was blocked by our content management system / safety policy.")

        # Should return empty string instead of raising
        res = await self.client.generate_text("Dangerous prompt")
        self.assertEqual(res, "")

    async def test_generate_structured_policy_error(self):
        # Mock structured LLM to raise policy error
        mock_structured_llm = AsyncMock()
        mock_structured_llm.ainvoke.side_effect = Exception("Policy violation detected.")

        self.client.llm = MagicMock()
        self.client.llm.with_structured_output.return_value = mock_structured_llm

        # Mock generate_text to also return empty for fallback
        # In reality LLMClient.generate_text will be called by fallback
        with patch.object(self.client, 'generate_text', AsyncMock(return_value="")):
             res = await self.client.generate_structured("Give me JSON", MockModel)

        # Should return a minimal valid model (with empty list)
        self.assertIsInstance(res, MockModel)
        self.assertEqual(res.items, [])

if __name__ == '__main__':
    unittest.main()
