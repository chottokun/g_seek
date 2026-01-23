import unittest
import asyncio
from unittest.mock import patch, MagicMock, AsyncMock
from deep_research_project.config.config import Configuration
from deep_research_project.tools.search_client import SearchClient
from deep_research_project.tools.content_retriever import ContentRetriever
from deep_research_project.core.state import SearchResult

class TestSearchClient(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.mock_config = MagicMock(spec=Configuration)
        self.mock_config.SEARCH_API = "duckduckgo"
        self.mock_config.MAX_SEARCH_RESULTS_PER_QUERY = 3

    @patch('deep_research_project.tools.search_client.DuckDuckGoSearchAPIWrapper')
    async def test_duckduckgo_initialization(self, mock_ddg):
        client = SearchClient(self.mock_config)
        self.assertTrue(hasattr(client, 'search_tool'))
        mock_ddg.assert_called_once()

    @patch('deep_research_project.tools.search_client.SearxSearchWrapper')
    async def test_searxng_initialization(self, mock_searx):
        self.mock_config.SEARCH_API = "searxng"
        self.mock_config.SEARXNG_BASE_URL = "http://localhost:8080"
        client = SearchClient(self.mock_config)
        self.assertTrue(hasattr(client, 'search_tool'))
        mock_searx.assert_called_once()

    @patch('deep_research_project.tools.search_client.DuckDuckGoSearchAPIWrapper')
    async def test_search_duckduckgo(self, mock_ddg):
        mock_instance = mock_ddg.return_value
        mock_instance.results.return_value = [
            {"title": "T1", "link": "L1", "snippet": "S1"}
        ]
        client = SearchClient(self.mock_config)
        results = await client.search("test query", num_results=1)

        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]['title'], "T1")
        self.assertEqual(results[0]['link'], "L1")
        mock_instance.results.assert_called_once()

class TestContentRetriever(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.mock_config = MagicMock(spec=Configuration)
        self.mock_config.MAX_TEXT_LENGTH_PER_SOURCE_CHARS = 100
        self.mock_config.PROCESS_PDF_FILES = True
        self.retriever = ContentRetriever(self.mock_config)

    @patch('httpx.AsyncClient')
    async def test_retrieve_and_extract_html(self, mock_client_class):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.headers = {"Content-Type": "text/html"}
        mock_response.text = "<html><body><p>Hello World</p></body></html>"
        mock_response.raise_for_status = MagicMock()

        # Mock the context manager and the get method
        mock_client_instance = mock_client_class.return_value.__aenter__.return_value
        mock_client_instance.get = AsyncMock(return_value=mock_response)

        content = await self.retriever.retrieve_and_extract("http://example.com")
        self.assertEqual(content, "Hello World")

    def test_extract_text_cleans_html(self):
        html = "<html><body><script>alert(1)</script><style>body{}</style><p>Text</p></body></html>"
        cleaned = self.retriever.extract_text(html)
        self.assertEqual(cleaned, "Text")

    @patch('deep_research_project.tools.content_retriever.PdfReader')
    @patch('httpx.AsyncClient')
    async def test_retrieve_and_extract_pdf(self, mock_client_class, mock_pdf_reader):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.headers = {"Content-Type": "application/pdf"}
        mock_response.content = b"%PDF-1.4"
        mock_response.raise_for_status = MagicMock()

        mock_client_instance = mock_client_class.return_value.__aenter__.return_value
        mock_client_instance.get = AsyncMock(return_value=mock_response)

        mock_pdf_instance = mock_pdf_reader.return_value
        mock_page = MagicMock()
        mock_page.extract_text.return_value = "PDF Content"
        mock_pdf_instance.pages = [mock_page]

        content = await self.retriever.retrieve_and_extract("http://example.com/file.pdf")
        self.assertEqual(content, "PDF Content")

    def test_apply_truncation(self):
        text = "A" * 200
        truncated = self.retriever._apply_truncation(text, "url")
        self.assertEqual(len(truncated), 100)

if __name__ == '__main__':
    unittest.main()
