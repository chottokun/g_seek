from typing import List, Optional, Callable, Dict
import logging
import asyncio
from deep_research_project.config.config import Configuration
from deep_research_project.core.state import ResearchState, SearchResult, Source, KnowledgeGraphModel
from deep_research_project.tools.llm_client import LLMClient
from deep_research_project.tools.search_client import SearchClient
from deep_research_project.tools.content_retriever import ContentRetriever
from deep_research_project.core.utils import split_text_into_chunks

logger = logging.getLogger(__name__)

class ExecutionManager:
    def __init__(self, llm_client: LLMClient, search_client: SearchClient, content_retriever: ContentRetriever, config: Configuration):
        self.llm_client = llm_client
        self.search_client = search_client
        self.content_retriever = content_retriever
        self.config = config

    async def generate_initial_query(self, state: ResearchState, section_title: str, section_desc: str) -> Optional[str]:
        topic = section_title
        desc = section_desc
        logger.info(f"Generating initial query for: {topic}")
        try:
            max_words = getattr(self.config, "MAX_QUERY_WORDS", 12)
            if state.language == "Japanese":
                prompt = (
                    f"以下のリサーチタスクのために、簡潔なWeb検索クエリ（最大{max_words}単語）を生成してください。\n"
                    f"メインテーマ: {state.research_topic}\n"
                    f"セクション: {topic}\n"
                    f"説明: {desc}\n\n"
                    f"クエリのみを出力してください。英語のソースも取得できるよう、適切であれば英語のクエリも検討してください。"
                )
            else:
                prompt = (
                    f"Generate a concise web search query (max {max_words} words) for the following research task.\n"
                    f"Main Topic: {state.research_topic}\n"
                    f"Section: {topic}\n"
                    f"Description: {desc}\n\n"
                    f"Output only the query."
                )
            query = await self.llm_client.generate_text(prompt=prompt)
            return query
        except Exception as e:
            logger.error(f"Error generating query: {e}")
            return None

    async def web_search(self, query: str, progress_callback: Optional[Callable[[str], None]] = None) -> List[SearchResult]:
        if not query: return []
        logger.info(f"Performing web search for: {query}")
        if progress_callback: await progress_callback(f"Searching web for: '{query}'...")
        try:
            results = await self.search_client.search(query, num_results=self.config.MAX_SEARCH_RESULTS_PER_QUERY)
            if progress_callback:
                if results:
                    results_str = "\n".join([f"- [{r['title']}]({r['link']})" for r in results])
                    await progress_callback(f"Found {len(results)} potential sources:\n{results_str}")
                else:
                    await progress_callback("No search results found.")
            return results
        except Exception as e:
            logger.error(f"Error during search: {e}")
            if progress_callback: await progress_callback(f"Search failed: {e}")
            return []

    async def summarize_sources(self, state: ResearchState, selected_results: List[SearchResult], progress_callback: Optional[Callable[[str], None]] = None):
        if not selected_results:
            state.new_information = "No sources selected."
            state.pending_source_selection = False
            return

        if progress_callback:
             sources_titles = ", ".join([r['title'] for r in selected_results])
             await progress_callback(f"Summarizing {len(selected_results)} sources: {sources_titles}...")

        all_chunk_summaries = []
        all_chunks_info = [] # Store all chunks to be processed in parallel
        if state.fetched_content is None: state.fetched_content = {}

        for result in selected_results:
            url = result['link']
            if url not in state.fetched_content:
                if self.config.USE_SNIPPETS_ONLY_MODE:
                    content = result.get('snippet', '')
                else:
                    content = await self.content_retriever.retrieve_and_extract(url)
                    if not content: content = result.get('snippet', '')
                state.fetched_content[url] = content

            content = state.fetched_content[url]
            chunks = split_text_into_chunks(content, self.config.SUMMARIZATION_CHUNK_SIZE_CHARS, self.config.SUMMARIZATION_CHUNK_OVERLAP_CHARS)
            all_chunks_info.extend([(chunk, url) for chunk in chunks])

        # Limit concurrency using Semaphore
        semaphore = asyncio.Semaphore(self.config.MAX_CONCURRENT_CHUNKS)

        async def summarize_chunk(chunk_info):
            chunk, url = chunk_info
            if state.is_interrupted: return None
            async with semaphore:
                if progress_callback: await progress_callback(f"Summarizing chunk from {url}...")
                if state.language == "Japanese":
                    prompt = f"リサーチクエリ: '{state.current_query}' のために、このセグメントを要約してください。\n\nセグメント:\n{chunk}"
                else:
                    prompt = f"Summarize this segment for the research query: '{state.current_query}'.\n\nSegment:\n{chunk}"
                return await self.llm_client.generate_text(prompt=prompt)

        # Execute parallel summarization
        if all_chunks_info:
            if progress_callback: await progress_callback(f"Starting parallel summarization for {len(all_chunks_info)} chunks...")
            summaries = await asyncio.gather(*[summarize_chunk(info) for info in all_chunks_info])
            all_chunk_summaries.extend([s for s in summaries if s])

        if state.is_interrupted:
             return

        if not all_chunk_summaries:
            state.new_information = "Could not summarize any content."
            if progress_callback: await progress_callback("No content could be summarized.")
        else:
            if progress_callback: await progress_callback("Synthesizing final summary for the query...")
            combined = "\n\n---\n\n".join(all_chunk_summaries)
            if state.language == "Japanese":
                prompt = f"これらの要約を、クエリ: '{state.current_query}' に関する一つの首尾一貫した要約にまとめてください。\n\n要約群:\n{combined}"
            else:
                prompt = f"Combine these summaries into one coherent summary for query: '{state.current_query}'.\n\nSummaries:\n{combined}"
            state.new_information = await self.llm_client.generate_text(prompt=prompt)
            state.accumulated_summary += f"\n\n## {state.current_query}\n{state.new_information}"
            if progress_callback: await progress_callback("Summary update complete.")

        for res in selected_results:
            if res['link'] not in [s['link'] for s in state.sources_gathered]:
                state.sources_gathered.append(Source(title=res['title'], link=res['link']))

        state.pending_source_selection = False

    async def extract_entities_and_relations(self, state: ResearchState, progress_callback: Optional[Callable[[str], None]] = None):
        if not state.new_information or len(state.new_information) < 20: return

        logger.info("Extracting entities and relations (structured).")
        if progress_callback: await progress_callback("Extracting entities and relations for knowledge graph...")
        if state.language == "Japanese":
            prompt = f"このテキストから主要なエンティティと関係を特定してください:\n\n{state.new_information}"
        else:
            prompt = f"Identify key entities and relationships from this text:\n\n{state.new_information}"

        try:
            kg_model = await self.llm_client.generate_structured(prompt=prompt, response_model=KnowledgeGraphModel)

            # Merge nodes
            existing_node_ids = {n['id'] for n in state.knowledge_graph_nodes}
            for n in kg_model.nodes:
                if n.id not in existing_node_ids:
                    state.knowledge_graph_nodes.append(n.model_dump())
                    existing_node_ids.add(n.id)

            # Merge edges (simplified deduplication based on source/target/label)
            existing_edge_keys = {(e['source'], e['target'], e.get('label')) for e in state.knowledge_graph_edges}
            for e in kg_model.edges:
                edge_key = (e.source, e.target, e.label)
                if edge_key not in existing_edge_keys:
                    state.knowledge_graph_edges.append(e.model_dump())
                    existing_edge_keys.add(edge_key)

            if progress_callback: await progress_callback(f"Knowledge graph now has {len(state.knowledge_graph_nodes)} nodes and {len(state.knowledge_graph_edges)} edges.")
        except Exception as e:
            logger.error(f"KG extraction failed: {e}")
            if progress_callback: await progress_callback("Knowledge graph extraction skipped or failed.")
