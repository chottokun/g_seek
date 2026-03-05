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
from deep_research_project.tools.cache_manager import CacheManager

logger = logging.getLogger(__name__)

class ContentRetriever:
    def __init__(self, config: Configuration, user_agent=None, progress_callback: Optional[Callable[[str], None]] = None):
        self.config = config
        self.user_agent = user_agent or getattr(config, "USER_AGENT", "DeepResearchBot/1.0")
        self.progress_callback = progress_callback
        self.headers = {"User-Agent": self.user_agent}
        cache_dir = getattr(self.config, "CACHE_DIR", ".cache")
        enable_caching = getattr(self.config, "ENABLE_CACHING", True)
        self.cache_manager = CacheManager(cache_dir=cache_dir, enabled=enable_caching)

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

    async def _resolve_and_validate_url(self, url: str) -> str:
        """
        Resolves the hostname in the URL and validates that it does not point
        to a private or restricted IP address if configured.
        Returns the resolved IP address.
        """
        parsed = urlparse(url)
        hostname = parsed.hostname
        if not hostname:
            raise ValueError(f"Invalid URL: {url}")

        try:
            # Check if hostname is already an IP
            ip_obj = ipaddress.ip_address(hostname)
            resolved_ips = [str(ip_obj)]
        except ValueError:
            # Resolve hostname to IP addresses
            loop = asyncio.get_running_loop()
            try:
                addr_info = await loop.run_in_executor(None, socket.getaddrinfo, hostname, 0)
                resolved_ips = [sockaddr[0] for _, _, _, _, sockaddr in addr_info]
            except socket.gaierror:
                raise ValueError(f"Could not resolve hostname: {hostname}")

        if not resolved_ips:
            raise ValueError(f"No IP addresses found for hostname: {hostname}")

        # Validate IPs if restricted
        if getattr(self.config, "BLOCK_LOCAL_IP_ACCESS", False):
            for ip in resolved_ips:
                ip_obj = ipaddress.ip_address(ip)
                if (ip_obj.is_private or ip_obj.is_loopback or
                    ip_obj.is_link_local or ip_obj.is_multicast or
                    ip_obj.is_reserved):
                    raise ValueError(f"Access to restricted IP {ip} is forbidden")

        # Return the first IP
        return resolved_ips[0]

    async def retrieve_and_extract(self, url: str, timeout: Optional[int] = None) -> str:
        """Asynchronously fetches content from a URL and extracts clean text with caching."""
        if getattr(self.config, "ENABLE_CACHING", True):
            cached = await self.cache_manager.get_content_cache(url)
            if cached:
                logger.info(f"Content for {url} retrieved from cache.")
                return cached

        logger.info(f"Attempting to retrieve and extract content from: {url}")
        request_timeout = timeout or getattr(self.config, "RETRIEVAL_TIMEOUT", 15)

        try:
            # We use follow_redirects=False to manually validate each redirect for security
            async with httpx.AsyncClient(headers=self.headers, follow_redirects=False, timeout=request_timeout) as client:
                current_url = url
                response = None
                max_redirects = 10

                for _ in range(max_redirects):
                    # Resolve and validate the URL before fetching
                    try:
                        resolved_ip = await self._resolve_and_validate_url(current_url)
                    except ValueError as ve:
                        logger.warning(f"URL validation failed for {current_url}: {ve}")
                        return ""

                    parsed_url = urlparse(current_url)
                    # Construct pinned URL using IP
                    # Handle both http and https, and preserve port if present
                    port_str = f":{parsed_url.port}" if parsed_url.port else ""

                    # Handle IPv6 brackets in URL
                    ip_for_url = resolved_ip
                    if ":" in resolved_ip and not resolved_ip.startswith("["):
                        ip_for_url = f"[{resolved_ip}]"

                    pinned_url = f"{parsed_url.scheme}://{ip_for_url}{port_str}{parsed_url.path}"
                    if parsed_url.query:
                        pinned_url += f"?{parsed_url.query}"
                    if parsed_url.fragment:
                        pinned_url += f"#{parsed_url.fragment}"

                    request_headers = self.headers.copy()
                    # Host header should include the port if it's non-standard
                    request_headers["Host"] = parsed_url.netloc

                    req = httpx.Request("GET", pinned_url, headers=request_headers)
                    if parsed_url.scheme == "https":
                        req.extensions["sni_hostname"] = parsed_url.hostname.encode()

                    response = await client.send(req)

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
                if (getattr(self.config, "PROCESS_PDF_FILES", True) and ("application/pdf" in content_type or current_url.lower().endswith(".pdf"))):
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

                    logger.warning(f"Unsupported content type '{content_type}' for {current_url}.")
                    return ""

                if getattr(self.config, "ENABLE_CACHING", True) and result:
                    await self.cache_manager.set_content_cache(url, result)
                return result

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
        limit = getattr(self.config, "MAX_TEXT_LENGTH_PER_SOURCE_CHARS", 0)
        if limit > 0 and len(text) > limit:
            logger.info(f"Truncating content from {url} to {limit} chars.")
            return text[:limit]
        return text
