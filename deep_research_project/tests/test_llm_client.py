import unittest
import os
import asyncio
from unittest.mock import patch, MagicMock, AsyncMock
from pydantic import BaseModel

from deep_research_project.config.config import Configuration
from deep_research_project.tools.llm_client import LLMClient

class MockModel(BaseModel):
    name: str
    value: int

class TestLLMClientAsync(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.mock_config = MagicMock(spec=Configuration)
        self.mock_config.LLM_PROVIDER = "openai"
        self.mock_config.LLM_MODEL = "gpt-4"
        self.mock_config.LLM_TEMPERATURE = 0.7
        self.mock_config.LLM_MAX_TOKENS = 1000
        self.mock_config.OPENAI_API_KEY = "test"
        self.mock_config.OPENAI_API_BASE_URL = None

        with patch('langchain_openai.ChatOpenAI'):
            self.client = LLMClient(self.mock_config)

    async def test_generate_text_async(self):
        # Mock ainvoke
        self.client.llm = AsyncMock()
        self.client.llm.ainvoke.return_value = MagicMock(content="Async response")

        res = await self.client.generate_text("Hello")
        self.assertEqual(res, "Async response")
        self.client.llm.ainvoke.assert_called_once_with("Hello")

    async def test_generate_structured_async(self):
        # Mock with_structured_output and its result
        mock_structured_llm = AsyncMock()
        mock_structured_llm.ainvoke.return_value = MockModel(name="test", value=123)

        self.client.llm = MagicMock()
        self.client.llm.with_structured_output.return_value = mock_structured_llm

        res = await self.client.generate_structured("Give me JSON", MockModel)

        self.assertEqual(res.name, "test")
        self.assertEqual(res.value, 123)
        self.client.llm.with_structured_output.assert_called_once_with(MockModel)

    async def test_placeholder_simulation(self):
        self.mock_config.LLM_PROVIDER = "placeholder_llm"
        client = LLMClient(self.mock_config)

        res = await client.generate_text("test")
        self.assertIn("Simulated", res)

        from deep_research_project.core.state import ResearchPlanModel
        res_struct = await client.generate_structured("structured research plan", ResearchPlanModel)
        self.assertIsInstance(res_struct, ResearchPlanModel)
        self.assertTrue(len(res_struct.sections) > 0)

if __name__ == '__main__':
    unittest.main()
