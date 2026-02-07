import asyncio
import unittest
import socket
from unittest.mock import MagicMock, AsyncMock, patch, call
from deep_research_project.config.config import Configuration
from deep_research_project.tools.content_retriever import ContentRetriever

class TestSSRF(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.config = MagicMock(spec=Configuration)
        self.config.MAX_TEXT_LENGTH_PER_SOURCE_CHARS = 1000
        self.config.PROCESS_PDF_FILES = False
        self.config.RETRIEVAL_TIMEOUT = 1
        self.retriever = ContentRetriever(self.config)

    async def test_block_private_ip_direct(self):
        url = "http://192.168.1.1"

        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client_cls.return_value.__aenter__.return_value = mock_client

            result = await self.retriever.retrieve_and_extract(url)

            self.assertEqual(result, "")
            mock_client.get.assert_not_called()

    async def test_block_localhost(self):
        url = "http://localhost"

        # Mock getaddrinfo to return 127.0.0.1
        # Note: We patch where it is looked up. Since content_retriever imports socket, and uses socket.getaddrinfo
        # we can patch socket.getaddrinfo.
        with patch("socket.getaddrinfo") as mock_getaddrinfo:
            mock_getaddrinfo.return_value = [(socket.AF_INET, socket.SOCK_STREAM, 6, '', ('127.0.0.1', 80))]

            with patch("httpx.AsyncClient") as mock_client_cls:
                mock_client = AsyncMock()
                mock_client_cls.return_value.__aenter__.return_value = mock_client

                result = await self.retriever.retrieve_and_extract(url)
                self.assertEqual(result, "")
                mock_client.get.assert_not_called()

    async def test_allow_public_ip(self):
        url = "http://example.com"

        with patch("socket.getaddrinfo") as mock_getaddrinfo:
            # 93.184.216.34 is example.com
            mock_getaddrinfo.return_value = [(socket.AF_INET, socket.SOCK_STREAM, 6, '', ('93.184.216.34', 80))]

            with patch("httpx.AsyncClient") as mock_client_cls:
                mock_client = AsyncMock()
                mock_client_cls.return_value.__aenter__.return_value = mock_client

                mock_response = MagicMock()
                mock_response.status_code = 200
                mock_response.headers = {"Content-Type": "text/html"}
                mock_response.text = "<html><body>Safe Content</body></html>"
                mock_response.is_redirect = False
                mock_response.raise_for_status = MagicMock()

                mock_client.get.return_value = mock_response

                result = await self.retriever.retrieve_and_extract(url)

                mock_client.get.assert_awaited_with(url)
                self.assertIn("Safe Content", result)

    async def test_block_redirect_to_private(self):
        url = "http://example.com/redirect"
        target_url = "http://192.168.1.1/secret"

        def getaddrinfo_side_effect(host, port, family=0, type=0, proto=0, flags=0):
            # Check host string (it might be bytes or str depending on usage, but usually str here)
            if "example.com" in str(host):
                return [(socket.AF_INET, socket.SOCK_STREAM, 6, '', ('93.184.216.34', 80))]
            elif "192.168.1.1" in str(host):
                return [(socket.AF_INET, socket.SOCK_STREAM, 6, '', ('192.168.1.1', 80))]
            raise socket.gaierror("Unknown host")

        with patch("socket.getaddrinfo", side_effect=getaddrinfo_side_effect):
            with patch("httpx.AsyncClient") as mock_client_cls:
                mock_client = AsyncMock()
                mock_client_cls.return_value.__aenter__.return_value = mock_client

                # First response: Redirect
                response1 = MagicMock()
                response1.status_code = 302
                response1.is_redirect = True
                response1.headers = {"Location": target_url}
                # When get is called first time, return redirect
                # When get is called second time (if it were), return forbidden/success

                mock_client.get.return_value = response1

                result = await self.retriever.retrieve_and_extract(url)

                self.assertEqual(result, "")

                # Verify get was called exactly once (for the initial URL)
                self.assertEqual(mock_client.get.await_count, 1)
                mock_client.get.assert_awaited_with(url)

if __name__ == "__main__":
    unittest.main()
