from langchain_community.utilities.duckduckgo_search import DuckDuckGoSearchAPIWrapper
from langchain_community.utilities import SearxSearchWrapper
from deep_research_project.config.config import Configuration
from deep_research_project.core.state import SearchResult
import logging
import asyncio

logger = logging.getLogger(__name__)

class SearchClient:
    def __init__(self, config: Configuration):
        self.config = config
        logger.info(f"Attempting to initialize SearchClient with API: {self.config.SEARCH_API}")
        if self.config.SEARCH_API == "duckduckgo":
            try:
                self.search_tool = DuckDuckGoSearchAPIWrapper()
                logger.info("Successfully initialized DuckDuckGo Search Client.")
            except Exception as e:
                logger.error(f"Failed to initialize DuckDuckGoSearchAPIWrapper: {e}", exc_info=True)
                raise ValueError(f"Failed to initialize DuckDuckGo client: {e}")
        elif self.config.SEARCH_API == "searxng":
            try:
                searxng_host = getattr(self.config, "SEARXNG_BASE_URL", "http://localhost:8080")
                k_results = getattr(self.config, "MAX_SEARCH_RESULTS_PER_QUERY", 3)
                searx_params = {"language": "ja", "safesearch": 1, "categories": "general"}
                headers = {
                    "User-Agent": "Mozilla/5.0 (compatible; SearxngBot/1.0; +https://github.com/searxng/searxng)"
                }
                self.search_tool = SearxSearchWrapper(
                    searx_host=searxng_host,
                    k=k_results,
                    params=searx_params,
                    headers=headers
                )
                logger.info("Initialized SearxSearchWrapper.")
            except Exception as e:
                logger.error(f"Failed to initialize SearxSearchWrapper: {e}", exc_info=True)
                raise ValueError(f"Failed to initialize Searxng client using SearxSearchWrapper: {e}")
        else:
            logger.error(f"Unsupported search API: {self.config.SEARCH_API}")
            raise ValueError(f"Unsupported search API: {self.config.SEARCH_API}")

    async def search(self, query: str, num_results: int = 3) -> list[SearchResult]:
        """Asynchronously performs a web search."""
        logger.info(f"Searching with {self.config.SEARCH_API} for: '{query}', num_results={num_results}")

        # Wrapping sync search in a thread to make it non-blocking in async context
        loop = asyncio.get_running_loop()
        try:
            return await loop.run_in_executor(None, self._sync_search, query, num_results)
        except Exception as e:
            logger.error(f"Error during search with {self.config.SEARCH_API} for query '{query}': {e}", exc_info=True)
            return []

    def _sync_search(self, query: str, num_results: int) -> list[SearchResult]:
        if self.config.SEARCH_API == "searxng":
            raw_results = self.search_tool.results(query, num_results)
        else:
            raw_results = self.search_tool.results(query=query, max_results=num_results)

        processed_results: list[SearchResult] = []
        if raw_results:
            for res in raw_results:
                processed_results.append(
                    SearchResult(
                        title=res.get("title", "N/A"),
                        link=res.get("link", "#"),
                        snippet=res.get("snippet", "No snippet available.")
                    )
                )
        logger.info(f"Found {len(processed_results)} results via SearchClient.")
        return processed_results
