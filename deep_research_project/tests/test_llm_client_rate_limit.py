import unittest
import asyncio
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
        self.mock_config.ENABLE_CACHING = False

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
            # Request 2: 0.525s (with 5% buffer)
            # Request 3: 1.05s (with 5% buffer)
            # Total duration should be at least 1.05s
            self.assertGreaterEqual(duration, 1.0)
            self.assertLess(duration, 1.6)

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
            # Should be almost instantaneous since we fixed it to return early
            self.assertLess(duration, 0.1)

    async def test_first_request_no_delay(self):
        with patch('langchain_openai.ChatOpenAI'):
            client = LLMClient(self.mock_config)
            client.llm = AsyncMock()
            client.llm.ainvoke.return_value = MagicMock(content="response")

            with patch('asyncio.sleep', new_callable=AsyncMock) as mock_sleep:
                await client.generate_text("p1")
                mock_sleep.assert_not_called()

    async def test_high_rpm_precision(self):
        # 10000 RPM means 1 request every 0.006 seconds
        self.mock_config.LLM_RATE_LIMIT_RPM = 10000
        with patch('langchain_openai.ChatOpenAI'):
            client = LLMClient(self.mock_config)
            client.llm = AsyncMock()
            client.llm.ainvoke.return_value = MagicMock(content="response")

            # Mock asyncio time to be constant to isolate the interval calculation
            # We must patch it where it is used in the event loop that LLMClient accesses
            loop = asyncio.get_event_loop()
            with patch.object(loop, 'time', return_value=100.0):
                await client.generate_text("p1")
                with patch('asyncio.sleep', new_callable=AsyncMock) as mock_sleep:
                    await client.generate_text("p2")
                    # Interval is (60/10000) * 1.05 = 0.0063
                    # Since time didn't advance, wait_time should be exactly limit_interval
                    self.assertTrue(mock_sleep.called)
                    args, _ = mock_sleep.call_args
                    self.assertAlmostEqual(args[0], 0.0063, places=4)

    async def test_concurrent_requests_serialized(self):
        self.mock_config.LLM_RATE_LIMIT_RPM = 60 # 1 req/sec
        with patch('langchain_openai.ChatOpenAI'):
            client = LLMClient(self.mock_config)
            client.llm = AsyncMock()
            client.llm.ainvoke.return_value = MagicMock(content="response")

            loop = asyncio.get_event_loop()
            with patch('asyncio.sleep', new_callable=AsyncMock) as mock_sleep:
                # Mock time to stay at 100.0
                with patch.object(loop, 'time', return_value=100.0):
                    # First request sets _last_request_time to 100.0
                    await client.generate_text("p1")

                    # These two should be serialized.
                    # 2nd request will see elapsed=0, sleep 1.05s, set last_time to 100.0 (since time didn't advance in our mock)
                    # 3rd request will see elapsed=0, sleep 1.05s, set last_time to 100.0
                    await asyncio.gather(
                        client.generate_text("p2"),
                        client.generate_text("p3")
                    )

                    self.assertEqual(mock_sleep.call_count, 2)
                    for call in mock_sleep.call_args_list:
                        args, _ = call
                        self.assertAlmostEqual(args[0], 1.05, places=4)

if __name__ == '__main__':
    unittest.main()
