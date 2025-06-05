from langchain_community.utilities.duckduckgo_search import DuckDuckGoSearchAPIWrapper
from langchain_community.utilities.searx_search import SearxNGSearchWrapper
from deep_research_project.config.config import Configuration
from deep_research_project.core.state import SearchResult
import logging
import requests

logger = logging.getLogger(__name__)

# The SearxngSearchClient class is no longer needed as we are using SearxNGSearchWrapper.
# class SearxngSearchClient:
#     def __init__(self, base_url="http://localhost:8080"):
#         self.base_url = base_url.rstrip("/")
#
#     def search(self, query, num_results=3):
#         import re
#         MAX_QUERY_LENGTH = 256
#         # 改行・余分な空白を除去し1行に整形
#         query = ' '.join(query.split())
#         # Markdownや記号、論理演算子、引用符などを除去
#         query = re.sub(r'[\*`\[\]"\'\-\_\=\~\|\^\$\#\@\!\?\<\>\(\)\{\}\:\;]', '', query)
#         # 先頭や末尾の空白を除去
#         query = query.strip() # Strip after cleaning symbols
#         # 先頭5単語だけをクエリに
#         # query = ' '.join(query.split()[:5])
#         # LLMの出力が長すぎる場合を考慮し、単語数で制限する（例: 最初の15単語）
#         query_words = query.split()
#         if len(query_words) > 15:
#             logger.warning(f"Query has too many words ({len(query_words)}). Truncating to 15 words.")
#             query = ' '.join(query_words[:15])
#
#         if len(query) > MAX_QUERY_LENGTH:
#             logger.warning(f"Query too long for Searxng (length={len(query)}). Truncating to {MAX_QUERY_LENGTH} chars.")
#             query = query[:MAX_QUERY_LENGTH]
#         logger.debug(f"Searxng送信クエリ: '{query}' (length={len(query)})")
#         params = {
#             "q": query,
#             "format": "json",
#             "language": "ja",
#             "safesearch": 1,
#             "categories": "general",
#             "count": num_results
#         }
#         headers = {
#             "User-Agent": "Mozilla/5.0 (compatible; SearxngBot/1.0; +https://github.com/searxng/searxng)"
#         }
#         try:
#             resp = requests.get(f"{self.base_url}/search", params=params, headers=headers, timeout=10)
#             try:
#                 resp.raise_for_status()
#             except requests.exceptions.HTTPError as http_err:
#                 if resp.status_code == 403:
#                     logger.warning("Searxng returned 403 Forbidden. クエリが不正か、サーバー側でブロックされています。検索結果なしとして返します。")
#                     return []
#                 else:
#                     logger.error(f"Searxng search failed: {http_err}", exc_info=True)
#                     return []
#             if 'application/json' not in resp.headers.get('Content-Type', ''):
#                 logger.error(f"Searxng returned non-JSON response: {resp.text[:200]}")
#                 return []
#             data = resp.json()
#             results = []
#             for r in data.get("results", []):
#                 results.append({
#                     "title": r.get("title", ""),
#                     "link": r.get("url", ""),
#                     "snippet": r.get("content", "")
#                 })
#             return results
#         except Exception as e:
#             logger.error(f"Searxng search failed: {e}", exc_info=True)
#             return []

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
                # Assuming MAX_SEARCH_RESULTS_PER_QUERY is available in config, else default to 3 for 'k'
                k_results = getattr(self.config, "MAX_SEARCH_RESULTS_PER_QUERY", 3)
                searx_params = {"language": "ja", "safesearch": 1, "categories": "general"}
                self.search_tool = SearxNGSearchWrapper(searxng_host=searxng_host, k=k_results, params=searx_params)
                logger.info("Initialized SearxNGSearchWrapper.")
            except Exception as e:
                logger.error(f"Failed to initialize SearxNGSearchWrapper: {e}", exc_info=True)
                raise ValueError(f"Failed to initialize Searxng client using SearxNGSearchWrapper: {e}")
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
            if self.config.SEARCH_API == "searxng":
                # The 'k' parameter in SearxNGSearchWrapper's constructor sets the default number of results.
                # If num_results is different from the initialized 'k', we might need to adjust,
                # but SearxNGSearchWrapper.results takes num_results which should override 'k'.
                raw_results = self.search_tool.results(query=query, num_results=num_results)
                processed_results: list[SearchResult] = []
                for res in raw_results: # Assuming results are dicts: {'title': ..., 'link': ..., 'snippet': ...}
                    processed_results.append(
                        SearchResult(
                            title=res.get("title", "N/A"),
                            link=res.get("link", "#"),
                            snippet=res.get("snippet", "No snippet available.")
                        )
                    )
                logger.info(f"Found {len(processed_results)} results via SearxNGSearchWrapper.")
                return processed_results

            if hasattr(self.search_tool, 'k') and self.config.SEARCH_API == "duckduckgo":
                 self.search_tool.k = num_results

            try:
                raw_results = self.search_tool.results(query=query, max_results=num_results)
            except Exception as e:
                logger.error(f"DuckDuckGo search failed: {e}", exc_info=True)
                return []

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

        except Exception as e:
            logger.error(f"Error during search with {self.config.SEARCH_API} for query '{query}': {e}", exc_info=True)
            return []

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
