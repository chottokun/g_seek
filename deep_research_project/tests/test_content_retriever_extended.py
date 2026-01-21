import unittest
from unittest.mock import MagicMock, patch
import io
from deep_research_project.config.config import Configuration
from deep_research_project.tools.content_retriever import ContentRetriever

class TestContentRetrieverExtended(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.mock_config = MagicMock(spec=Configuration)
        self.mock_config.MAX_TEXT_LENGTH_PER_SOURCE_CHARS = 100
        self.mock_config.PROCESS_PDF_FILES = True
        self.retriever = ContentRetriever(self.mock_config)

    def test_apply_truncation(self):
        text = "A" * 200
        truncated = self.retriever._apply_truncation(text, "http://test.com")
        self.assertEqual(len(truncated), 100)
        self.assertEqual(truncated, "A" * 100)

        self.mock_config.MAX_TEXT_LENGTH_PER_SOURCE_CHARS = 0
        not_truncated = self.retriever._apply_truncation(text, "http://test.com")
        self.assertEqual(len(not_truncated), 200)

    def test_extract_text_cleans_html(self):
        html = """
        <html>
            <head><title>Test</title></head>
            <body>
                <nav>Navigation</nav>
                <header>Header</header>
                <main>
                    <h1>Title</h1>
                    <p>Some important text.</p>
                    <script>alert('noise');</script>
                    <style>.noise { color: red; }</style>
                </main>
                <footer>Footer</footer>
            </body>
        </html>
        """
        extracted = self.retriever.extract_text(html)
        self.assertIn("Title", extracted)
        self.assertIn("Some important text.", extracted)
        self.assertNotIn("Navigation", extracted)
        self.assertNotIn("Header", extracted)
        self.assertNotIn("Footer", extracted)
        self.assertNotIn("alert", extracted)

    @patch('deep_research_project.tools.content_retriever.PdfReader')
    def test_sync_process_pdf(self, mock_pdf_reader):
        # Mocking PdfReader behavior
        mock_page1 = MagicMock()
        mock_page1.extract_text.return_value = "Page 1 content"
        mock_page2 = MagicMock()
        mock_page2.extract_text.return_value = "Page 2 content"
        
        mock_reader_instance = mock_pdf_reader.return_value
        mock_reader_instance.pages = [mock_page1, mock_page2]
        
        result = self.retriever._sync_process_pdf(b"dummy pdf bytes", "http://test.pdf")
        
        self.assertIn("Page 1 content", result)
        self.assertIn("Page 2 content", result)
        self.assertIn("\n\n", result)

    @patch('httpx.AsyncClient.get')
    async def test_retrieve_unsupported_type(self, mock_get):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.headers = {"Content-Type": "application/zip"}
        mock_get.return_value = mock_response
        
        result = await self.retriever.retrieve_and_extract("http://test.com/file.zip")
        self.assertEqual(result, "")

if __name__ == '__main__':
    unittest.main()
