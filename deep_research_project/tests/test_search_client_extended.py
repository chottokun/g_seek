import unittest
from unittest.mock import MagicMock, patch
from deep_research_project.config.config import Configuration
from deep_research_project.tools.search_client import SearchClient

class TestSearchClientExtended(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.mock_config = MagicMock(spec=Configuration)
        self.mock_config.SEARCH_API = "searxng"
        self.mock_config.SEARXNG_BASE_URL = "http://localhost:8080"
        self.mock_config.MAX_SEARCH_RESULTS_PER_QUERY = 3

    @patch('deep_research_project.tools.search_client.SearxSearchWrapper')
    def test_searxng_initialization(self, mock_searx):
        client = SearchClient(self.mock_config)
        self.assertIsNotNone(client.search_tool)
        mock_searx.assert_called_once()

    @patch('deep_research_project.tools.search_client.SearxSearchWrapper')
    async def test_searxng_search_parsing(self, mock_searx):
        # Setup mock results
        mock_instance = mock_searx.return_value
        mock_instance.results.return_value = [
            {"title": "Result 1", "link": "http://r1.com", "snippet": "Snippet 1"},
            {"title": "Result 2", "link": "http://r2.com", "snippet": "Snippet 2"}
        ]
        
        client = SearchClient(self.mock_config)
        results = await client.search("test query", num_results=2)
        
        self.assertEqual(len(results), 2)
        self.assertEqual(results[0]['title'], "Result 1")
        self.assertEqual(results[1]['link'], "http://r2.com")

    @patch('deep_research_project.tools.search_client.DuckDuckGoSearchAPIWrapper')
    async def test_search_error_handling(self, mock_ddg):
        self.mock_config.SEARCH_API = "duckduckgo"
        mock_instance = mock_ddg.return_value
        mock_instance.results.side_effect = Exception("Search API Down")
        
        client = SearchClient(self.mock_config)
        results = await client.search("test query")
        
        self.assertEqual(results, [])

if __name__ == '__main__':
    unittest.main()
