import unittest
import asyncio
from unittest.mock import MagicMock, AsyncMock, patch
from pydantic import BaseModel
from deep_research_project.tools.llm_client import LLMClient, LLMPolicyError
from deep_research_project.config.config import Configuration

class MockModel(BaseModel):
    items: list[str]

class TestLLMClientPolicy(unittest.IsolatedAsyncioTestCase):
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
        self.mock_config.LLM_RETRY_BASE_DELAY = 0.01

        with patch('langchain_openai.ChatOpenAI'):
            self.client = LLMClient(self.mock_config)

    async def test_invoke_with_retry_policy_error(self):
        """Test that various policy-related error messages raise LLMPolicyError."""
        self.client.llm = AsyncMock()

        policy_messages = [
            "This request was blocked by our content management system.",
            "Safety policy violation.",
            "content_filter triggered.",
            "The response was filtered.",
            "Access blocked due to policy.",
            "Management policy violation."
        ]

        async def mock_call():
            raise Exception(msg)

        for msg in policy_messages:
            with self.subTest(msg=msg):
                with self.assertRaises(LLMPolicyError) as cm:
                    await self.client._invoke_with_retry(mock_call)
                self.assertIn("LLM Policy Violation", str(cm.exception))

    async def test_invoke_with_retry_no_retry_on_policy_error(self):
        """Test that LLMPolicyError is not retried."""
        mock_call = AsyncMock(side_effect=Exception("blocked by policy"))

        with self.assertRaises(LLMPolicyError):
            await self.client._invoke_with_retry(mock_call)

        # Should only be called once because policy errors are not retried
        self.assertEqual(mock_call.call_count, 1)

    async def test_generate_text_recovery(self):
        """Test that generate_text returns an empty string on LLMPolicyError."""
        # Mock _invoke_with_retry to raise LLMPolicyError
        with patch.object(self.client, '_invoke_with_retry', AsyncMock(side_effect=LLMPolicyError("Policy violation"))):
            res = await self.client.generate_text("test prompt")
            self.assertEqual(res, "")

    async def test_generate_structured_native_policy_recovery(self):
        """Test that generate_structured falls back to fallback on native policy error."""
        # Mock native call to raise LLMPolicyError
        mock_structured_llm = AsyncMock()
        mock_structured_llm.ainvoke.side_effect = LLMPolicyError("Native policy error")
        self.client.llm = MagicMock()
        self.client.llm.with_structured_output.return_value = mock_structured_llm

        # Mock fallback to return a specific result
        expected_result = MockModel(items=["fallback"])
        with patch.object(self.client, '_generate_structured_fallback', AsyncMock(return_value=expected_result)) as mock_fallback:
            res = await self.client.generate_structured("test prompt", MockModel)
            self.assertEqual(res, expected_result)
            mock_fallback.assert_called_once()

    async def test_generate_structured_fallback_policy_error(self):
        """Test that _generate_structured_fallback handles policy error during generate_text."""
        # Mock generate_text to raise LLMPolicyError (which it might do if we call it directly,
        # but LLMClient.generate_text itself catches it and returns "".
        # Wait, _generate_structured_fallback calls self.generate_text.
        # If self.generate_text catches it, it returns "".
        # Then _generate_structured_fallback will try to parse "" and fail.

        with patch.object(self.client, 'generate_text', AsyncMock(side_effect=LLMPolicyError("Fallback policy error"))):
            res = await self.client._generate_structured_fallback("test prompt", MockModel)
            # Should return a minimal valid model (empty list)
            self.assertIsInstance(res, MockModel)
            self.assertEqual(res.items, [])

if __name__ == '__main__':
    unittest.main()
