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
