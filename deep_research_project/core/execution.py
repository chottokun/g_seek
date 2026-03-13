import asyncio
import logging
from typing import List, Optional, Callable
from pydantic import BaseModel
from deep_research_project.config.config import Configuration
from deep_research_project.tools.llm_client import LLMClient
from deep_research_project.tools.search_client import SearchClient
from deep_research_project.tools.content_retriever import ContentRetriever
from deep_research_project.core.state import SearchResult
from deep_research_project.core.utils import split_text_into_chunks
from deep_research_project.core.prompts import (
    SUMMARIZE_CHUNK_PROMPT_JA, SUMMARIZE_CHUNK_PROMPT_EN,
    COMBINE_SUMMARIES_PROMPT_JA, COMBINE_SUMMARIES_PROMPT_EN,
    RELEVANCE_SCORING_PROMPT_JA, RELEVANCE_SCORING_PROMPT_EN
)

logger = logging.getLogger(__name__)

class ResearchExecutor:
    def __init__(self, config: Configuration, llm_client: LLMClient, 
                 search_client: SearchClient, content_retriever: ContentRetriever):
        self.config = config
        self.llm_client = llm_client
        self.search_client = search_client
        self.content_retriever = content_retriever
        self.chunk_semaphore = asyncio.Semaphore(getattr(self.config, "MAX_CONCURRENT_CHUNKS", 5))
        self.retrieval_semaphore = asyncio.Semaphore(getattr(self.config, "MAX_CONCURRENT_RETRIEVALS", 5))

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
        
        async def get_content(res):
            url = res.link
            if url not in fetched_content:
                async with self.retrieval_semaphore:
                    if progress_callback: await progress_callback(f"Retrieving: {url}")
                    if getattr(self.config, "USE_SNIPPETS_ONLY_MODE", False):
                        content = res.snippet
                    else:
                        content = await self.content_retriever.retrieve_and_extract(url)
                        if not content: content = res.snippet
                    fetched_content[url] = content
            return url, fetched_content[url]

        # Parallel retrieval
        await asyncio.gather(*[get_content(res) for res in results])

        for res in results:
            url = res.link
            content = fetched_content[url]
            chunks = split_text_into_chunks(content, 
                                            getattr(self.config, "SUMMARIZATION_CHUNK_SIZE_CHARS", 10000), 
                                            getattr(self.config, "SUMMARIZATION_CHUNK_OVERLAP_CHARS", 500))
            all_chunks_info.extend([(chunk, url) for chunk in chunks])

        if not all_chunks_info:
            return "Could not retrieve any content to summarize."

        # Parallel summarization of chunks
        async def summarize_chunk(chunk, url):
            async with self.chunk_semaphore:
                if progress_callback: await progress_callback(f"Summarizing chunk from {url}...")
                if language == "Japanese":
                    prompt = SUMMARIZE_CHUNK_PROMPT_JA.format(query=query, chunk=chunk)
                else:
                    prompt = SUMMARIZE_CHUNK_PROMPT_EN.format(query=query, chunk=chunk)
                return await self.llm_client.generate_text(prompt=prompt)

        chunk_summaries = await asyncio.gather(*[summarize_chunk(c, u) for c, u in all_chunks_info], return_exceptions=True)

        valid_summaries = []
        for s in chunk_summaries:
            if isinstance(s, Exception):
                logger.error(f"Error summarizing chunk: {s}")
            elif s:
                # Defensive check: ensure s is a string (handles potential list returns or stale cache)
                if isinstance(s, list):
                    s = " ".join([str(item) for item in s])
                elif not isinstance(s, str):
                    s = str(s)
                    
                valid_summaries.append(s)
        
        if not valid_summaries:
            return "Failed to generate any summaries from the segments."

        # Final synthesis
        combined = "\n\n---\n\n".join(valid_summaries)
        if language == "Japanese":
            prompt = COMBINE_SUMMARIES_PROMPT_JA.format(query=query, combined=combined)
        else:
            prompt = COMBINE_SUMMARIES_PROMPT_EN.format(query=query, combined=combined)
        
        return await self.llm_client.generate_text(prompt=prompt)

    async def score_relevance_batch(self, query: str, results: List[SearchResult], language: str) -> List[float]:
        """
        Scores the relevance of multiple search results to the query in a single LLM call to save RPM.
        Returns a list of scores between 0.0 and 1.0.
        """
        if not results:
            return []

        # Construct a batch prompt
        items_text = ""
        for i, res in enumerate(results):
            items_text += f"\n---\nRESULT ID: {i}\nTITLE: {res.title}\nSNIPPET: {res.snippet}\n"

        if language == "Japanese":
            prompt = f"""クエリ: {query}

以下の検索結果（複数）について、それぞれクエリへの関連性を 0.0〜1.0 でスコアリングしてください。
- 1.0: 非常に関連性が高い
- 0.5: やや関連性がある
- 0.0: 全く関連性がない

回答は以下のJSON形式のみで返してください：
{{"scores": [スコア0, スコア1, ...]}}

検索結果リスト:{items_text}
"""
        else:
            prompt = f"""Query: {query}

Score the relevance of each of the following search results to the query on a scale of 0.0 to 1.0.
- 1.0: Highly relevant
- 0.5: Somewhat relevant
- 0.0: Not relevant

Respond ONLY with a JSON object in this format:
{{"scores": [score0, score1, ...]}}

Search Results:{items_text}
"""
        
        try:
            class ScoreBatch(BaseModel):
                scores: List[float]
            
            try:
                response = await self.llm_client.generate_structured(prompt, ScoreBatch)
                scores = [max(0.0, min(1.0, s)) for s in response.scores]
            except Exception as e:
                logger.warning(f"Structured batch scoring failed: {e}. Falling back to individual scoring.")
                raise # Let the outer try-except handle the fallback
            
            # Ensure we have the same number of scores as results
            if len(scores) != len(results):
                logger.warning(f"Batch score count mismatch: expected {len(results)}, got {len(scores)}. Padding/truncating.")
                if len(scores) < len(results):
                    scores.extend([0.5] * (len(results) - len(scores)))
                else:
                    scores = scores[:len(results)]
            
            return scores
        except Exception as e:
            logger.warning(f"Failed batch relevance scoring: {e}. Falling back to individual scoring.")
            # Fallback to individual scoring if batch fails
            individual_scores = await asyncio.gather(*[self.score_relevance(query, r, language) for r in results])
            return list(individual_scores)

    async def score_relevance(self, query: str, result: SearchResult, language: str) -> float:
        """
        Scores the relevance of a search result to the query using LLM.
        Returns a score between 0.0 (not relevant) and 1.0 (highly relevant).
        """
        if language == "Japanese":
            prompt = RELEVANCE_SCORING_PROMPT_JA.format(
                query=query, title=result.title, snippet=result.snippet
            )
        else:
            prompt = RELEVANCE_SCORING_PROMPT_EN.format(
                query=query, title=result.title, snippet=result.snippet
            )
        
        try:
            response = await self.llm_client.generate_text(prompt=prompt)
            # Extract numeric value from response
            score_str = response.strip().split()[0]  # Get first token
            score = float(score_str)
            return max(0.0, min(1.0, score))  # Clamp to [0.0, 1.0]
        except (ValueError, IndexError, AttributeError) as e:
            logger.warning(f"Failed to parse relevance score from LLM response: {response}. Error: {e}. Defaulting to 0.5")
            return 0.5  # Default to neutral score on parse failure

    async def filter_by_relevance(self, query: str, results: List[SearchResult], 
                                   language: str, use_snippet: bool = True,
                                   threshold: Optional[float] = None,
                                   progress_callback: Optional[Callable] = None) -> List[SearchResult]:
        """
        Filters search results by relevance score.
        
        Args:
            query: The search query
            results: List of search results to filter
            language: Language for LLM prompts
            use_snippet: If True, score based on snippet; if False, score based on full content
            threshold: Optional custom threshold (overrides config)
            progress_callback: Optional callback for progress reporting
        
        Returns:
            Filtered list of search results, sorted by relevance score (descending)
        """
        if not results:
            return []
        
        # Use custom threshold or fall back to config
        relevance_threshold = threshold if threshold is not None else getattr(self.config, "RELEVANCE_THRESHOLD", 0.4) # Slightly lower for more results
        
        # Batch scoring to save RPM
        batch_size = getattr(self.config, "BATCH_SIZE_RELEVANCE", 5)
        scored_results = []
        
        logger.info(f"Scoring {len(results)} search results for relevance (batch size: {batch_size}, threshold: {relevance_threshold})...")
        
        for i in range(0, len(results), batch_size):
            batch = results[i:i + batch_size]
            if progress_callback: await progress_callback(f"Scoring batch {i//batch_size + 1} ({len(batch)} results)...")
            
            batch_scores = await self.score_relevance_batch(query, batch, language)
            for result, score in zip(batch, batch_scores):
                result.relevance_score = score
                logger.debug(f"Relevance score for '{result.title}': {score:.2f}")
                scored_results.append(result)
        
        # Filter by threshold
        relevant = [r for r in scored_results if r.relevance_score >= relevance_threshold]
        logger.info(f"Found {len(relevant)}/{len(results)} results above threshold {relevance_threshold:.2f}. Total unique sources being passed: {len(relevant)}")
        
        # Sort by relevance score (descending) and take top MAX_RELEVANT_RESULTS
        filtered = sorted(relevant, key=lambda r: r.relevance_score, reverse=True)
        filtered = filtered[:getattr(self.config, "MAX_RELEVANT_RESULTS", 5)]
        
        return filtered
