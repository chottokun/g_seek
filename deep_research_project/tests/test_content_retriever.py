import unittest
import asyncio
import socket
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

    @patch("socket.getaddrinfo")
    async def test_retrieve_and_extract_html(self, mock_getaddrinfo):
        mock_getaddrinfo.return_value = [(None, None, None, None, ("127.0.0.1", 80))]

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.headers = {"Content-Type": "text/html"}
        mock_response.text = "<html><body><p>Content</p></body></html>"
        mock_response.raise_for_status = MagicMock()

        retriever = ContentRetriever(self.mock_config)
        # We need to mock AsyncClient as a whole or mock the context manager
        with patch("httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client.send.return_value = mock_response
            mock_client.__aenter__.return_value = mock_client
            mock_client_class.return_value = mock_client

            text = await retriever.retrieve_and_extract("http://example.com")
            self.assertEqual(text, "Content")

    @patch("socket.getaddrinfo")
    @patch("deep_research_project.tools.content_retriever.PdfReader")
    @patch("httpx.AsyncClient")
    async def test_retrieve_and_extract_pdf(self, mock_client_class, mock_pdf_reader, mock_getaddrinfo):
        mock_getaddrinfo.return_value = [(None, None, None, None, ("127.0.0.1", 80))]

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.headers = {"Content-Type": "application/pdf"}
        mock_response.content = b"pdf content"
        mock_response.raise_for_status = MagicMock()

        mock_client = AsyncMock()
        mock_client.send.return_value = mock_response
        mock_client.__aenter__.return_value = mock_client
        mock_client_class.return_value = mock_client

        mock_page = MagicMock()
        mock_page.extract_text.return_value = "PDF Page Content"
        mock_pdf_reader.return_value.pages = [mock_page]

        retriever = ContentRetriever(self.mock_config)
        text = await retriever.retrieve_and_extract("http://example.com/test.pdf")
        self.assertIn("PDF Page Content", text)

    async def test_resolve_and_validate_url_invalid_url(self):
        retriever = ContentRetriever(self.mock_config)
        with self.assertRaisesRegex(ValueError, "Invalid URL"):
            await retriever._resolve_and_validate_url("http://")

    async def test_resolve_and_validate_url_already_ip(self):
        retriever = ContentRetriever(self.mock_config)
        ip = await retriever._resolve_and_validate_url("http://1.1.1.1")
        self.assertEqual(ip, "1.1.1.1")

    @patch("socket.getaddrinfo")
    async def test_resolve_and_validate_url_gaierror(self, mock_getaddrinfo):
        mock_getaddrinfo.side_effect = socket.gaierror("Name or service not known")
        retriever = ContentRetriever(self.mock_config)
        with self.assertRaisesRegex(ValueError, "Could not resolve hostname"):
            await retriever._resolve_and_validate_url("http://nonexistent.example.com")

    @patch("socket.getaddrinfo")
    async def test_resolve_and_validate_url_no_ips(self, mock_getaddrinfo):
        mock_getaddrinfo.return_value = []
        retriever = ContentRetriever(self.mock_config)
        with self.assertRaisesRegex(ValueError, "No IP addresses found"):
            await retriever._resolve_and_validate_url("http://example.com")

    @patch("socket.getaddrinfo")
    async def test_resolve_and_validate_url_restricted_ip(self, mock_getaddrinfo):
        self.mock_config.BLOCK_LOCAL_IP_ACCESS = True
        mock_getaddrinfo.return_value = [(None, None, None, None, ("127.0.0.1", 80))]
        retriever = ContentRetriever(self.mock_config)
        with self.assertRaisesRegex(ValueError, "Access to restricted IP"):
            await retriever._resolve_and_validate_url("http://localhost")

if __name__ == "__main__":
    unittest.main()
