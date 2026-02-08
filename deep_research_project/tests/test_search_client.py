import unittest
import asyncio
from unittest.mock import patch, MagicMock

from deep_research_project.config.config import Configuration
from deep_research_project.tools.search_client import SearchClient
# SearchResult is a TypedDict
from deep_research_project.core.state import SearchResult

class TestSearchClient(unittest.IsolatedAsyncioTestCase):

    async def asyncSetUp(self):
        self.mock_config = MagicMock(spec=Configuration)
        self.mock_config.SEARCH_API = "duckduckgo"
        # Set default values for other config attributes to avoid AttributeErrors
        self.mock_config.SEARXNG_BASE_URL = "http://localhost:8080"
        self.mock_config.MAX_SEARCH_RESULTS_PER_QUERY = 3
        self.mock_config.SEARXNG_LANGUAGE = "en"
        self.mock_config.SEARXNG_SAFESEARCH = 1
        self.mock_config.SEARXNG_CATEGORIES = "general"
        self.mock_config.USER_AGENT = "TestAgent"

    async def test_init_duckduckgo_success(self):
        self.mock_config.SEARCH_API = "duckduckgo"
        with patch('deep_research_project.tools.search_client.DuckDuckGoSearchAPIWrapper') as MockDDG:
            client = SearchClient(self.mock_config)
            MockDDG.assert_called_once()
            # Verify that search_tool is set
            self.assertTrue(hasattr(client, 'search_tool'))

    async def test_init_duckduckgo_failure(self):
        self.mock_config.SEARCH_API = "duckduckgo"
        with patch('deep_research_project.tools.search_client.DuckDuckGoSearchAPIWrapper', side_effect=Exception("DDG Error")):
            with self.assertRaises(ValueError) as context:
                SearchClient(self.mock_config)
            self.assertIn("Failed to initialize DuckDuckGo client", str(context.exception))

    async def test_init_searxng_success(self):
        self.mock_config.SEARCH_API = "searxng"
        with patch('deep_research_project.tools.search_client.SearxSearchWrapper') as MockSearx:
            client = SearchClient(self.mock_config)
            MockSearx.assert_called_once()
            _, kwargs = MockSearx.call_args
            self.assertEqual(kwargs['searx_host'], "http://localhost:8080")
            self.assertEqual(kwargs['k'], 3)

    async def test_init_searxng_failure(self):
        self.mock_config.SEARCH_API = "searxng"
        with patch('deep_research_project.tools.search_client.SearxSearchWrapper', side_effect=Exception("Searx Error")):
            with self.assertRaises(ValueError) as context:
                SearchClient(self.mock_config)
            self.assertIn("Failed to initialize Searxng client", str(context.exception))

    async def test_init_unsupported_api(self):
        self.mock_config.SEARCH_API = "unsupported"
        with self.assertRaises(ValueError) as context:
            SearchClient(self.mock_config)
        self.assertIn("Unsupported search API", str(context.exception))

    async def test_search_duckduckgo(self):
        self.mock_config.SEARCH_API = "duckduckgo"
        with patch('deep_research_project.tools.search_client.DuckDuckGoSearchAPIWrapper') as MockDDG:
            mock_tool = MockDDG.return_value
            mock_tool.results.return_value = [
                {"title": "Test Title", "link": "http://test.com", "snippet": "Test Snippet"}
            ]

            client = SearchClient(self.mock_config)
            results = await client.search("test query", num_results=2)

            self.assertEqual(len(results), 1)
            self.assertEqual(results[0].title, "Test Title")
            self.assertEqual(results[0].link, "http://test.com")
            self.assertEqual(results[0].snippet, "Test Snippet")
            mock_tool.results.assert_called_once_with(query="test query", max_results=2)

    async def test_search_searxng(self):
        self.mock_config.SEARCH_API = "searxng"
        with patch('deep_research_project.tools.search_client.SearxSearchWrapper') as MockSearx:
            mock_tool = MockSearx.return_value
            mock_tool.results.return_value = [
                {"title": "Searx Title", "link": "http://searx.com", "snippet": "Searx Snippet"}
            ]

            client = SearchClient(self.mock_config)
            results = await client.search("test query", num_results=2)

            self.assertEqual(len(results), 1)
            self.assertEqual(results[0].title, "Searx Title")
            mock_tool.results.assert_called_once_with("test query", num_results=2)

    async def test_search_searxng_fallback(self):
        self.mock_config.SEARCH_API = "searxng"
        with patch('deep_research_project.tools.search_client.SearxSearchWrapper') as MockSearx:
            mock_tool = MockSearx.return_value

            # Simulate TypeError on first call, success on second
            def side_effect(*args, **kwargs):
                if 'num_results' in kwargs:
                    raise TypeError("unexpected keyword argument 'num_results'")
                return [{"title": "Fallback Title", "link": "http://fallback.com", "snippet": "Fallback Snippet"}]

            mock_tool.results.side_effect = side_effect

            client = SearchClient(self.mock_config)
            results = await client.search("test query", num_results=2)

            self.assertEqual(len(results), 1)
            self.assertEqual(results[0].title, "Fallback Title")

            # Check calls
            # 1. Called with num_results (failed)
            # 2. Called without num_results (succeeded)
            self.assertEqual(mock_tool.results.call_count, 2)

            call_args_list = mock_tool.results.call_args_list
            self.assertEqual(call_args_list[0].args, ("test query",))
            self.assertEqual(call_args_list[0].kwargs, {'num_results': 2})

            self.assertEqual(call_args_list[1].args, ("test query",))
            self.assertEqual(call_args_list[1].kwargs, {})

    async def test_search_error_handling(self):
        self.mock_config.SEARCH_API = "duckduckgo"
        with patch('deep_research_project.tools.search_client.DuckDuckGoSearchAPIWrapper') as MockDDG:
            mock_tool = MockDDG.return_value
            mock_tool.results.side_effect = Exception("Search failed")

            client = SearchClient(self.mock_config)
            results = await client.search("fail query")

            self.assertEqual(results, [])

if __name__ == '__main__':
    unittest.main()
