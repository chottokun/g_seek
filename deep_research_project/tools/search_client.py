from langchain_community.utilities.duckduckgo_search import DuckDuckGoSearchAPIWrapper
from ..config.config import Configuration # Adjusted import path
from ..core.state import SearchResult # Adjusted import path
import logging

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
                # Propagate the error after logging, or handle it by setting a Null-like search tool
                raise ValueError(f"Failed to initialize DuckDuckGo client: {e}")
        # Add other search APIs here later if needed, e.g., Tavily
        # elif self.config.SEARCH_API == "tavily":
        #     if not self.config.TAVILY_API_KEY:
        #         logger.error("Tavily API key not found in configuration for search client.")
        #         raise ValueError("Tavily API key not found in configuration for search client.")
        #     # self.search_tool = TavilySearchResults(api_key=self.config.TAVILY_API_KEY) # Example
        #     logger.info("Initialized Tavily Search Client.")
        else:
            logger.error(f"Unsupported search API: {self.config.SEARCH_API}")
            raise ValueError(f"Unsupported search API: {self.config.SEARCH_API}")

    def search(self, query: str, num_results: int = 3) -> list[SearchResult]:
        logger.info(f"Searching with {self.config.SEARCH_API} for: '{query}', num_results={num_results}")
        try:
            # The DuckDuckGoSearchAPIWrapper has a 'k' parameter for number of results in its constructor,
            # but the .results() method also takes num_results.
            # Let's rely on passing num_results to .results() as it's more direct.
            # If 'k' is needed for other tools, this structure is fine.
            if hasattr(self.search_tool, 'k') and self.config.SEARCH_API == "duckduckgo": # Be specific if 'k' is DDG only
                 self.search_tool.k = num_results # Set 'k' if it's used by this tool instance

            # The .results() method in DuckDuckGoSearchAPIWrapper should take 'query' and 'max_results'.
            # Checking langchain source: DuckDuckGoSearchAPIWrapper.results(query, max_results)
            raw_results = self.search_tool.results(query=query, max_results=num_results)

            processed_results: list[SearchResult] = []
            if raw_results: # Ensure raw_results is not None and is iterable
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

        except Exception as e:
            logger.error(f"Error during search with {self.config.SEARCH_API} for query '{query}': {e}", exc_info=True)
            return [] # Return empty list on error

# Example Usage (for testing this module)
if __name__ == "__main__":
    # Basic logging for example usage
    # Ensure this basicConfig is only for this example execution
    logging.basicConfig(level=logging.DEBUG,
                        format='%(asctime)s - %(levelname)s - %(name)s - %(module)s.%(funcName)s:%(lineno)d - %(message)s')
    logger.info("Testing SearchClient...")
    try:
        # Create a dummy Configuration object for testing
        class MockConfiguration:
            SEARCH_API = "duckduckgo"
            TAVILY_API_KEY = None # Not needed for duckduckgo
            MAX_SEARCH_RESULTS_PER_QUERY = 2
            LOG_LEVEL = "DEBUG" # For this example

        mock_config = MockConfiguration()
        search_client = SearchClient(config=mock_config)

        results = search_client.search(query="latest advancements in AI", num_results=mock_config.MAX_SEARCH_RESULTS_PER_QUERY)

        if results:
            logger.info("Search Results:")
            for i, res in enumerate(results):
                logger.info(f"Result {i+1}:")
                logger.info(f"  Title: {res['title']}")
                logger.info(f"  Link: {res['link']}")
                logger.info(f"  Snippet: {res['snippet']}")
        else:
            logger.info("No results returned or an error occurred.")

    except Exception as e:
        logger.error(f"Error in SearchClient example: {e}", exc_info=True)
# No traceback import needed if exc_info=True is used with logger.error
