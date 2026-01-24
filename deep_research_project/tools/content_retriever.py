import httpx
from bs4 import BeautifulSoup
import logging
import io
import asyncio
from pypdf import PdfReader
from pypdf.errors import PdfReadError
from deep_research_project.config.config import Configuration
from typing import Optional, Callable

logger = logging.getLogger(__name__)

class ContentRetriever:
    def __init__(self, config: Configuration, user_agent="DeepResearchBot/1.0", progress_callback: Optional[Callable[[str], None]] = None):
        self.config = config
        self.user_agent = user_agent
        self.progress_callback = progress_callback
        self.headers = {"User-Agent": self.user_agent}

    def extract_text(self, html_content: str, url: str = "") -> str:
        """Extracts and cleans text content from HTML using BeautifulSoup."""
        if not html_content:
            return ""
        try:
            soup = BeautifulSoup(html_content, "html.parser")
            for script_or_style in soup(["script", "style", "header", "footer", "nav", "aside"]):
                script_or_style.decompose()

            text = soup.get_text(separator='\n', strip=True)
            lines = [line.strip() for line in text.splitlines()]
            cleaned_lines = []
            for line in lines:
                if line:
                    cleaned_lines.append(' '.join(line.split()))

            text = "\n\n".join(cleaned_lines)

            if not text and url:
                logger.info(f"No text extracted from {url} after parsing.")
            return text
        except Exception as e:
            logger.error(f"Error parsing HTML and extracting text (URL: {url if url else 'N/A'}): {e}")
            return ""

    async def _call_progress(self, message: str):
        """Helper to call progress_callback regardless of whether it's sync or async."""
        if not self.progress_callback:
            return

        try:
            if asyncio.iscoroutinefunction(self.progress_callback):
                await self.progress_callback(message)
            else:
                self.progress_callback(message)
        except Exception as e:
            logger.error(f"Error in progress_callback: {e}")

    async def retrieve_and_extract(self, url: str, timeout: int = 15) -> str:
        """Asynchronously fetches content from a URL and extracts clean text."""
        logger.info(f"Attempting to retrieve and extract content from: {url}")

        try:
            async with httpx.AsyncClient(headers=self.headers, follow_redirects=True, timeout=timeout) as client:
                response = await client.get(url)
                response.raise_for_status()

                content_type = response.headers.get("Content-Type", "").lower()

                # PDF Processing
                if (self.config.PROCESS_PDF_FILES and ("application/pdf" in content_type or url.lower().endswith(".pdf"))):
                    return await self._process_pdf(response.content, url)

                # HTML Processing
                elif "text/html" in content_type:
                    text_content = self.extract_text(response.text, url=url)
                    if text_content:
                        await self._call_progress(f"Successfully extracted {len(text_content)} chars from HTML: {url}")
                    return self._apply_truncation(text_content, url)

                # Fallback for plain text
                elif "text/" in content_type:
                    return self._apply_truncation(response.text.strip(), url)

                else:
                    logger.warning(f"Unsupported content type '{content_type}' for {url}.")
                    return ""

        except Exception as e:
            logger.error(f"Error retrieving {url}: {e}")
            return ""

    async def _process_pdf(self, pdf_bytes: bytes, url: str) -> str:
        await self._call_progress(f"PDF detected. Processing: {url}")

        # PdfReader is CPU-bound, run in executor
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, self._sync_process_pdf, pdf_bytes, url)

    def _sync_process_pdf(self, pdf_bytes: bytes, url: str) -> str:
        try:
            with io.BytesIO(pdf_bytes) as f:
                reader = PdfReader(f)
                pages = []
                for page in reader.pages:
                    t = page.extract_text()
                    if t: pages.append(t)
                text = "\n\n".join(pages)
                return self._apply_truncation(text, url)
        except Exception as e:
            logger.error(f"Error processing PDF {url}: {e}")
            return ""

    def _apply_truncation(self, text: str, url: str) -> str:
        limit = self.config.MAX_TEXT_LENGTH_PER_SOURCE_CHARS
        if limit > 0 and len(text) > limit:
            logger.info(f"Truncating content from {url} to {limit} chars.")
            return text[:limit]
        return text
