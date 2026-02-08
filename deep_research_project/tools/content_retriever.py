import socket
import ipaddress
import logging
import io
import asyncio
import httpx
from bs4 import BeautifulSoup
from pypdf import PdfReader
from urllib.parse import urlparse, urljoin
from deep_research_project.config.config import Configuration
from typing import Optional, Callable

logger = logging.getLogger(__name__)

class ContentRetriever:
    def __init__(self, config: Configuration, user_agent=None, progress_callback: Optional[Callable[[str], None]] = None):
        self.config = config
        self.user_agent = user_agent or getattr(config, "USER_AGENT", "DeepResearchBot/1.0")
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
            cleaned_lines = [
                " ".join(line.split()) for line in text.splitlines() if line.strip()
            ]

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

    async def _validate_url(self, url: str):
        """Validates that the URL does not point to a private or restricted IP address if configured."""
        if not getattr(self.config, "BLOCK_LOCAL_IP_ACCESS", False):
            return

        try:
            parsed = urlparse(url)
            hostname = parsed.hostname
            if not hostname:
                raise ValueError(f"Invalid URL: {url}")

            # Resolve hostname to IP addresses
            loop = asyncio.get_running_loop()
            # Use run_in_executor for blocking socket call
            addr_info = await loop.run_in_executor(None, socket.getaddrinfo, hostname, 0)

            for _, _, _, _, sockaddr in addr_info:
                ip = sockaddr[0]
                ip_obj = ipaddress.ip_address(ip)

                # Check for private, loopback, or other restricted ranges
                if (ip_obj.is_private or ip_obj.is_loopback or
                    ip_obj.is_link_local or ip_obj.is_multicast or
                    ip_obj.is_reserved):
                    raise ValueError(f"Access to restricted IP {ip} is forbidden")

        except socket.gaierror:
            # If we can't resolve it, it might be invalid or internal DNS that fails externally.
            raise ValueError(f"Could not resolve hostname: {parsed.hostname}")
        except Exception as e:
            if isinstance(e, ValueError):
                raise e
            raise ValueError(f"Error validating URL {url}: {e}")

    async def retrieve_and_extract(self, url: str, timeout: Optional[int] = None) -> str:
        """Asynchronously fetches content from a URL and extracts clean text."""
        logger.info(f"Attempting to retrieve and extract content from: {url}")

        request_timeout = timeout or getattr(self.config, "RETRIEVAL_TIMEOUT", 15)

        try:
            # We use follow_redirects=False to manually validate each redirect for security
            async with httpx.AsyncClient(headers=self.headers, follow_redirects=False, timeout=request_timeout) as client:
                current_url = url
                response = None
                max_redirects = 10

                for _ in range(max_redirects):
                    # Validate the URL before fetching (only if BLOCK_LOCAL_IP_ACCESS is enabled)
                    try:
                        await self._validate_url(current_url)
                    except ValueError as ve:
                        logger.warning(f"URL validation failed: {ve}")
                        return ""

                    response = await client.get(current_url)

                    # Check for redirects
                    if response.is_redirect:
                        location = response.headers.get("Location")
                        if not location:
                            break

                        # Handle relative redirects
                        current_url = urljoin(current_url, location)
                        continue
                    else:
                        break
                else:
                    logger.warning(f"Max redirects exceeded for {url}")
                    return ""

                if response is None:
                     return ""

                response.raise_for_status()

                content_type = response.headers.get("Content-Type", "").lower()

                # PDF Processing
                if (self.config.PROCESS_PDF_FILES and ("application/pdf" in content_type or current_url.lower().endswith(".pdf"))):
                    return await self._process_pdf(response.content, current_url)

                # HTML Processing
                elif "text/html" in content_type:
                    text_content = self.extract_text(response.text, url=current_url)
                    if text_content:
                        await self._call_progress(f"Successfully extracted {len(text_content)} chars from HTML: {current_url}")
                    return self._apply_truncation(text_content, current_url)

                # Fallback for plain text
                elif "text/" in content_type:
                    return self._apply_truncation(response.text.strip(), current_url)

                else:
                    logger.warning(f"Unsupported content type '{content_type}' for {current_url}.")
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
