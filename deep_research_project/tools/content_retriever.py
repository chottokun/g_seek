import requests
from bs4 import BeautifulSoup
import logging
import io
from pypdf import PdfReader
from pypdf.errors import PdfReadError
from deep_research_project.config.config import Configuration # For type hinting

logger = logging.getLogger(__name__)

class ContentRetriever:
    def __init__(self, config: Configuration, user_agent="DeepResearchBot/1.0"):
        self.config = config # Store config
        self.user_agent = user_agent
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": self.user_agent})

    # fetch_html can be removed or kept as an internal helper if direct HTML fetching is needed elsewhere,
    # but retrieve_and_extract will now handle the primary fetching logic.
    # For now, let's keep it, but it won't be directly used by the refactored retrieve_and_extract.

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
        logger.info(f"Attempting to retrieve and extract content from: {url}")
        text_content = ""
        try:
            response = self.session.get(url, timeout=timeout, allow_redirects=True, stream=False)
            response.raise_for_status()
            content_type = response.headers.get("Content-Type", "").lower()

            # PDF Processing Path
            if (self.config.PROCESS_PDF_FILES and
                ("application/pdf" in content_type or url.lower().endswith(".pdf"))):
                logger.info(f"Processing as PDF: {url}")
                pdf_content_bytes = response.content
                if not pdf_content_bytes:
                    logger.warning(f"No content bytes received for PDF {url}")
                    return ""
                try:
                    with io.BytesIO(pdf_content_bytes) as pdf_file_like_object:
                        reader = PdfReader(pdf_file_like_object)
                        extracted_pages = []
                        for i, page in enumerate(reader.pages):
                            try:
                                page_text = page.extract_text()
                                if page_text:
                                    extracted_pages.append(page_text)
                            except Exception as e_page: # Catch errors per page
                                logger.warning(f"Error extracting text from page {i+1} of PDF {url}: {e_page}")
                        text_content = "\n\n".join(extracted_pages)
                        if text_content:
                            logger.info(f"Successfully extracted text from PDF {url} (raw length: {len(text_content)} chars).")
                        else:
                            logger.warning(f"No text extracted from PDF {url} after processing pages.")
                except PdfReadError as e_pdf_read:
                    logger.error(f"PyPDF PdfReadError processing PDF {url}: {e_pdf_read}. This might be an encrypted or corrupted PDF.")
                    return "" # Return empty for PDF read errors
                except Exception as e_pdf:
                    logger.error(f"Error processing PDF {url} with pypdf: {e_pdf}", exc_info=True)
                    return "" # Return empty for other PDF errors

            # HTML Processing Path
            elif "text/html" in content_type:
                logger.info(f"Processing as HTML: {url}")
                html_content = response.text
                if html_content:
                    text_content = self.extract_text(html_content, url=url)
                    # self.extract_text already logs success/failure and length.
                else:
                    logger.warning(f"No HTML content in response from {url}")
                    return ""

            # PDF link but processing disabled
            elif (not self.config.PROCESS_PDF_FILES and
                  ("application/pdf" in content_type or url.lower().endswith(".pdf"))):
                logger.info(f"PDF processing is disabled. Skipping PDF: {url}")
                return "" # Return empty as PDF processing is off

            # Other content types
            else:
                logger.warning(f"Unsupported content type '{content_type}' for {url}. Attempting to treat as plain text if possible.")
                if "text/" in content_type: # Fallback for generic text types
                    try:
                        text_content = response.text.strip()
                        if text_content:
                             logger.info(f"Extracted raw text from {url} (type: {content_type}, length: {len(text_content)} chars).")
                        else:
                            logger.warning(f"Content type {content_type} for {url} but no text could be decoded or text is empty.")
                            return "" # Return empty if no actual text after strip
                    except Exception as e_text:
                        logger.warning(f"Could not decode content of type {content_type} as text for {url}: {e_text}")
                        return ""
                else: # Not a known text type or PDF
                    logger.warning(f"Content type {content_type} for {url} is not processable as text.")
                    return "" # Return empty for unprocessable types

            # Apply MAX_TEXT_LENGTH_PER_SOURCE_CHARS to the extracted text_content (HTML or PDF)
            # Ensure text_content is a string before len() and slicing
            if not isinstance(text_content, str): # Should ideally always be str by now or ""
                logger.warning(f"text_content is not a string for {url} (type: {type(text_content)}). Skipping truncation.")
            else:
                limit = self.config.MAX_TEXT_LENGTH_PER_SOURCE_CHARS
                if limit > 0 and len(text_content) > limit:
                    logger.info(f"Extracted content from {url} (original length: {len(text_content)}) exceeds limit ({limit}). Truncating.")
                    text_content = text_content[:limit]
                    logger.debug(f"Truncated content length for {url}: {len(text_content)}")

            return text_content

        except requests.exceptions.RequestException as e:
            logger.error(f"Error fetching URL {url}: {e}")
            return ""
        except Exception as e_general: # Catch any other unexpected errors
            logger.error(f"An unexpected error occurred while retrieving/extracting {url}: {e_general}", exc_info=True)
            return ""

if __name__ == "__main__":
    # For basic testing, we need a mock Configuration object
    class MockConfig:
        PROCESS_PDF_FILES = True
        MAX_TEXT_LENGTH_PER_SOURCE_CHARS = 0 # No limit for this test run
        # Add other config attributes if ContentRetriever's __init__ or methods use them

    mock_conf = MockConfig()

    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(name)s - %(message)s')
    retriever = ContentRetriever(config=mock_conf) # Pass mock_conf

    # Test URLs (some might work, some might fail or be blocked)
    test_urls = [
        "https://www.streamlit.io/",
        "https://www.python.org/psf/mission/",
        "https://nonexistentwebsite.example.com", # Expected to fail request
        "https://www.google.com", # Often blocks scrapers, might return non-HTML or fail
        "https://www.w3.org/WAI/ER/tests/xhtml/testfiles/resources/pdf/dummy.pdf" # A known PDF link
    ]

    # Example with PDF processing disabled for one URL
    mock_conf_no_pdf = MockConfig()
    mock_conf_no_pdf.PROCESS_PDF_FILES = False
    retriever_no_pdf = ContentRetriever(config=mock_conf_no_pdf)
    print(f"--- Testing PDF URL with PDF processing disabled: {test_urls[4]} ---")
    content_no_pdf = retriever_no_pdf.retrieve_and_extract(test_urls[4])
    if content_no_pdf:
        print(f"Extracted Content (first 300 chars): {content_no_pdf[:300]}...")
    else:
        print("No content extracted or error occurred (as expected for disabled PDF processing).")
    print("--- End Test --- \n")


    # Example with text truncation
    mock_conf_truncate = MockConfig()
    mock_conf_truncate.MAX_TEXT_LENGTH_PER_SOURCE_CHARS = 150
    retriever_truncate = ContentRetriever(config=mock_conf_truncate)
    print(f"--- Testing HTML URL with truncation: {test_urls[0]} ---")
    content_truncate = retriever_truncate.retrieve_and_extract(test_urls[0])
    if content_truncate:
        print(f"Extracted Content (length: {len(content_truncate)}): {content_truncate}...") # Print all if short
    else:
        print("No content extracted or error occurred.")
    print("--- End Test --- \n")


    for t_url in test_urls:
        print(f"--- Testing URL: {t_url} (PDF processing ON, no truncation default) ---")
        content = retriever.retrieve_and_extract(t_url)
        if content:
            print(f"Extracted Content (first 300 chars): {content[:300]}...")
            if len(content) > 300: print("...")
        else:
            print("No content extracted or error occurred.")
        print("--- End Test --- \n")
