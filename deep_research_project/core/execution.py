import asyncio
import logging
from typing import List, Optional, Callable
from deep_research_project.config.config import Configuration
from deep_research_project.tools.llm_client import LLMClient
from deep_research_project.tools.search_client import SearchClient, SearchResult
from deep_research_project.tools.content_retriever import ContentRetriever
from deep_research_project.core.utils import split_text_into_chunks

logger = logging.getLogger(__name__)

class ResearchExecutor:
    def __init__(self, config: Configuration, llm_client: LLMClient, 
                 search_client: SearchClient, content_retriever: ContentRetriever):
        self.config = config
        self.llm_client = llm_client
        self.search_client = search_client
        self.content_retriever = content_retriever
        self.semaphore = asyncio.Semaphore(self.config.MAX_CONCURRENT_CHUNKS)

    async def search(self, query: str, num_results: int) -> List[SearchResult]:
        """Performs web search and returns results."""
        logger.info(f"Searching for: {query}")
        return await self.search_client.search(query, num_results=num_results)

    async def retrieve_and_summarize(self, results: List[SearchResult], query: str, 
                                   language: str, fetched_content: Optional[dict] = None, 
                                   progress_callback: Optional[Callable] = None) -> str:
        """Retrieves full content for search results and generates summaries in parallel."""
        if fetched_content is None:
            # We need to be careful here: if the caller expects us to update a persistent dict,
            # they must pass it. If they pass None, we use a local one for this session.
            fetched_content = {}
        
        all_chunks_info = []
        
        for res in results:
            url = res.link
            if url not in fetched_content:
                if progress_callback: await progress_callback(f"Retrieving: {url}")
                if self.config.USE_SNIPPETS_ONLY_MODE:
                    content = res.snippet
                else:
                    content = await self.content_retriever.retrieve_and_extract(url)
                    if not content: content = res.snippet
                fetched_content[url] = content

            content = fetched_content[url]
            chunks = split_text_into_chunks(content, 
                                            self.config.SUMMARIZATION_CHUNK_SIZE_CHARS, 
                                            self.config.SUMMARIZATION_CHUNK_OVERLAP_CHARS)
            all_chunks_info.extend([(chunk, url) for chunk in chunks])

        if not all_chunks_info:
            return "Could not retrieve any content to summarize."

        # Parallel summarization of chunks
        async def summarize_chunk(chunk, url):
            async with self.semaphore:
                if progress_callback: await progress_callback(f"Summarizing chunk from {url}...")
                if language == "Japanese":
                    prompt = f"リサーチクエリ: '{query}' のために、このセグメントを要約してください。\n\nセグメント:\n{chunk}"
                else:
                    prompt = f"Summarize this segment for the research query: '{query}'.\n\nSegment:\n{chunk}"
                return await self.llm_client.generate_text(prompt=prompt)

        chunk_summaries = await asyncio.gather(*[summarize_chunk(c, u) for c, u in all_chunks_info])
        valid_summaries = [s for s in chunk_summaries if s]
        
        if not valid_summaries:
            return "Failed to generate any summaries from the segments."

        # Final synthesis
        combined = "\n\n---\n\n".join(valid_summaries)
        if language == "Japanese":
            prompt = f"これらの要約を、クエリ: '{query}' に関する一つの首尾一貫した要約にまとめてください。\n\n要約群:\n{combined}"
        else:
            prompt = f"Combine these summaries into one coherent summary for query: '{query}'.\n\nSummaries:\n{combined}"
        
        return await self.llm_client.generate_text(prompt=prompt)

    async def score_relevance(self, query: str, result: SearchResult, language: str) -> float:
        """
        Scores the relevance of a search result to the query using LLM.
        Returns a score between 0.0 (not relevant) and 1.0 (highly relevant).
        """
        if language == "Japanese":
            prompt = f"""クエリ: {query}

検索結果:
タイトル: {result.title}
スニペット: {result.snippet}

このページがクエリに関連しているかを 0.0〜1.0 でスコアリングしてください。
- 1.0: 非常に関連性が高い
- 0.5: やや関連性がある
- 0.0: 全く関連性がない

スコアのみを数値で回答してください（例: 0.8）
"""
        else:
            prompt = f"""Query: {query}

Search Result:
Title: {result.title}
Snippet: {result.snippet}

Score the relevance of this page to the query on a scale of 0.0 to 1.0.
- 1.0: Highly relevant
- 0.5: Somewhat relevant
- 0.0: Not relevant

Respond with only the numeric score (e.g., 0.8)
"""
        
        try:
            response = await self.llm_client.generate_text(prompt=prompt)
            # Extract numeric value from response
            score_str = response.strip().split()[0]  # Get first token
            score = float(score_str)
            return max(0.0, min(1.0, score))  # Clamp to [0.0, 1.0]
        except (ValueError, IndexError) as e:
            logger.warning(f"Failed to parse relevance score from LLM response: {response}. Error: {e}. Defaulting to 0.5")
            return 0.5  # Default to neutral score on parse failure

    async def filter_by_relevance(self, query: str, results: List[SearchResult], 
                                   language: str, use_snippet: bool = True,
                                   threshold: Optional[float] = None) -> List[SearchResult]:
        """
        Filters search results by relevance score.
        
        Args:
            query: The search query
            results: List of search results to filter
            language: Language for LLM prompts
            use_snippet: If True, score based on snippet; if False, score based on full content
            threshold: Optional custom threshold (overrides config)
        
        Returns:
            Filtered list of search results, sorted by relevance score (descending)
        """
        if not results:
            return []
        
        # Use custom threshold or fall back to config
        relevance_threshold = threshold if threshold is not None else self.config.RELEVANCE_THRESHOLD
        
        # Parallel scoring of all results
        async def score_result(result: SearchResult) -> SearchResult:
            score = await self.score_relevance(query, result, language)
            result.relevance_score = score
            logger.debug(f"Relevance score for '{result.title}': {score:.2f}")
            return result
        
        logger.info(f"Scoring {len(results)} search results for relevance...")
        scored_results = await asyncio.gather(*[score_result(r) for r in results])
        
        # Filter by threshold
        relevant = [r for r in scored_results if r.relevance_score >= relevance_threshold]
        logger.info(f"Found {len(relevant)}/{len(results)} results above threshold {relevance_threshold:.2f}")
        
        # Sort by relevance score (descending) and take top MAX_RELEVANT_RESULTS
        filtered = sorted(relevant, key=lambda r: r.relevance_score, reverse=True)
        filtered = filtered[:self.config.MAX_RELEVANT_RESULTS]
        
        return filtered
