import unittest
from unittest.mock import patch, MagicMock
from deep_research_project.tools.search_client import SearchClient, SearchResult
from deep_research_project.config.config import Configuration
import asyncio

class TestSearchClient(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.config = MagicMock(spec=Configuration)
        self.config.SEARCH_API = "duckduckgo"

    @patch('deep_research_project.tools.search_client.DuckDuckGoSearchAPIWrapper')
    async def test_search_raises_exception(self, MockDDG):
        # Setup mock to raise exception
        mock_tool = MockDDG.return_value
        mock_tool.results.side_effect = Exception("Search API Error")

        client = SearchClient(self.config)

        # New behavior: raises Exception
        with self.assertRaises(Exception) as context:
            await client.search("query")

        self.assertIn("Search API Error", str(context.exception))

if __name__ == '__main__':
    unittest.main()
