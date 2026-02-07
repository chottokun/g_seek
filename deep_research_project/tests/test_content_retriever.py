import unittest
import asyncio
from unittest.mock import MagicMock, AsyncMock, patch
from deep_research_project.config.config import Configuration
from deep_research_project.tools.content_retriever import ContentRetriever

class TestContentRetriever(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.mock_config = MagicMock(spec=Configuration)
        self.mock_config.MAX_TEXT_LENGTH_PER_SOURCE_CHARS = 0
        self.mock_config.PROCESS_PDF_FILES = True

    def test_extract_text(self):
        retriever = ContentRetriever(self.mock_config)
        html = "<html><head><title>Test</title></head><body><h1>Hello</h1><p>World</p><script>alert('hidden')</script></body></html>"
        text = retriever.extract_text(html)
        self.assertIn("Hello", text)
        self.assertIn("World", text)
        self.assertNotIn("alert", text)

    async def test_call_progress_sync(self):
        sync_callback = MagicMock()
        retriever = ContentRetriever(self.mock_config, progress_callback=sync_callback)
        await retriever._call_progress("test message")
        sync_callback.assert_called_once_with("test message")

    async def test_call_progress_async(self):
        async_callback = AsyncMock()
        retriever = ContentRetriever(self.mock_config, progress_callback=async_callback)
        await retriever._call_progress("test message")
        async_callback.assert_awaited_once_with("test message")

    async def test_retrieve_and_extract_html(self):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.headers = {"Content-Type": "text/html"}
        mock_response.text = "<html><body><p>Content</p></body></html>"
        mock_response.raise_for_status = MagicMock()

        retriever = ContentRetriever(self.mock_config)
        # We need to mock AsyncClient as a whole or mock the context manager
        with patch("httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client.get.return_value = mock_response
            mock_client.__aenter__.return_value = mock_client
            mock_client_class.return_value = mock_client

            text = await retriever.retrieve_and_extract("http://example.com")
            self.assertEqual(text, "Content")

    @patch("deep_research_project.tools.content_retriever.PdfReader")
    @patch("httpx.AsyncClient")
    async def test_retrieve_and_extract_pdf(self, mock_client_class, mock_pdf_reader):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.headers = {"Content-Type": "application/pdf"}
        mock_response.content = b"pdf content"
        mock_response.raise_for_status = MagicMock()

        mock_client = AsyncMock()
        mock_client.get.return_value = mock_response
        mock_client.__aenter__.return_value = mock_client
        mock_client_class.return_value = mock_client

        mock_page = MagicMock()
        mock_page.extract_text.return_value = "PDF Page Content"
        mock_pdf_reader.return_value.pages = [mock_page]

        retriever = ContentRetriever(self.mock_config)
        text = await retriever.retrieve_and_extract("http://example.com/test.pdf")
        self.assertIn("PDF Page Content", text)

    @patch("deep_research_project.tools.content_retriever.PdfReader")
    @patch("httpx.AsyncClient")
    async def test_retrieve_and_extract_pdf_error(self, mock_client_class, mock_pdf_reader):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.headers = {"Content-Type": "application/pdf"}
        mock_response.content = b"corrupt pdf"
        mock_response.raise_for_status = MagicMock()

        mock_client = AsyncMock()
        mock_client.get.return_value = mock_response
        mock_client.__aenter__.return_value = mock_client
        mock_client_class.return_value = mock_client

        # Mock PdfReader to raise an exception
        mock_pdf_reader.side_effect = Exception("PDF parsing failed")

        retriever = ContentRetriever(self.mock_config)
        text = await retriever.retrieve_and_extract("http://example.com/test.pdf")

        # Should return empty string on error
        self.assertEqual(text, "")

if __name__ == "__main__":
    unittest.main()
