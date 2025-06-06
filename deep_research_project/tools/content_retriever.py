import requests
from bs4 import BeautifulSoup
import logging

logger = logging.getLogger(__name__)

class ContentRetriever:
    def __init__(self, user_agent="DeepResearchBot/1.0"):
        self.user_agent = user_agent
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": self.user_agent})

    def fetch_html(self, url: str, timeout: int = 10) -> str | None:
        """Fetches HTML content from a URL."""
        try:
            response = self.session.get(url, timeout=timeout, allow_redirects=True)
            response.raise_for_status()  # Raise HTTPError for bad responses (4XX or 5XX)

            # Check content type to ensure it's likely HTML
            content_type = response.headers.get("Content-Type", "").lower()
            if "text/html" not in content_type:
                logger.warning(f"Content type for {url} is '{content_type}', not text/html. Skipping.")
                return None

            return response.text
        except requests.exceptions.RequestException as e:
            logger.error(f"Error fetching URL {url}: {e}")
            return None

    def extract_text(self, html_content: str, url: str = "") -> str:
        """Extracts and cleans text content from HTML using BeautifulSoup."""
        if not html_content:
            return ""
        try:
            soup = BeautifulSoup(html_content, "html.parser")

            # Remove script and style elements
            for script_or_style in soup(["script", "style", "header", "footer", "nav", "aside"]):
                script_or_style.decompose()

            # Get text
            text = soup.get_text(separator='\n', strip=True)

            # Basic cleaning: reduce multiple newlines to two, and multiple spaces to one
            lines = [line.strip() for line in text.splitlines()]
            cleaned_lines = []
            for line in lines:
                if line: # Keep non-empty lines
                    # Replace multiple spaces with a single space within the line
                    cleaned_lines.append(' '.join(line.split()))

            # Join lines, ensuring not too many blank lines overall
            text = "\n\n".join(cleaned_lines) # Max two newlines between blocks

            if not text and url:
                logger.info(f"No text extracted from {url} after parsing.")
            elif not text:
                logger.info("No text extracted from HTML content after parsing.")

            return text
        except Exception as e:
            logger.error(f"Error parsing HTML and extracting text (URL: {url if url else 'N/A'}): {e}")
            return ""

    def retrieve_and_extract(self, url: str, timeout: int = 10) -> str:
        """Fetches HTML from a URL and extracts clean text."""
        logger.info(f"Retrieving and extracting content from: {url}")
        html_content = self.fetch_html(url, timeout=timeout)
        if html_content:
            text_content = self.extract_text(html_content, url=url)
            logger.info(f"Successfully extracted text from {url} (length: {len(text_content)} chars).")
            return text_content
        logger.warning(f"Failed to retrieve or extract text from {url}.")
        return ""

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(name)s - %(message)s')
    retriever = ContentRetriever()

    # Test URLs (some might work, some might fail or be blocked)
    test_urls = [
        "https://www.streamlit.io/",
        "https://www.python.org/psf/mission/",
        "https://nonexistentwebsite.example.com", # Expected to fail
        "https://www.google.com" # Often blocks scrapers
    ]

    for t_url in test_urls:
        print(f"--- Testing URL: {t_url} ---")
        content = retriever.retrieve_and_extract(t_url)
        if content:
            print(f"Extracted Content (first 300 chars):\
{content[:300]}...")
        else:
            print("No content extracted or error occurred.")
        print("--- End Test --- \
")
