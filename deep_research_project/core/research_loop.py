from deep_research_project.config.config import Configuration
from deep_research_project.config.prompts import PROMPTS
from .state import (
    ResearchState, SearchResult, Source,
    ResearchPlanModel, KnowledgeGraphModel
)

from deep_research_project.tools.llm_client import LLMClient
from deep_research_project.tools.search_client import SearchClient
from deep_research_project.tools.content_retriever import ContentRetriever
import logging
import json
import asyncio
from typing import List, Optional, Callable

logger = logging.getLogger(__name__)


def split_text_into_chunks(text: str, chunk_size: int, chunk_overlap: int) -> List[str]:
    """Splits a given text into overlapping chunks."""
    if not text: return []
    if chunk_size <= 0: raise ValueError("Chunk size must be positive.")
    if chunk_overlap < 0 or chunk_overlap >= chunk_size:
        raise ValueError("Invalid chunk overlap.")

    text_len = len(text)
    if text_len <= chunk_size: return [text]

    chunks = []
    idx = 0
    while idx < text_len:
        end_idx = idx + chunk_size
        chunks.append(text[idx:end_idx])
        if end_idx >= text_len: break
        idx += (chunk_size - chunk_overlap)
    return chunks


class ResearchLoop:
    def __init__(self, config: Configuration, state: ResearchState, progress_callback: Optional[Callable[[str], None]] = None):
        self.config = config
        self.state = state
        self.interactive_mode = config.INTERACTIVE_MODE
        self.progress_callback = progress_callback

        self.llm_client = LLMClient(config)
        self.search_client = SearchClient(config)
        self.content_retriever = ContentRetriever(config=self.config, progress_callback=progress_callback)

    def _get_prompt(self, key: str, **kwargs) -> str:
        """Retrieves and formats a prompt based on language and key."""
        language = self.state.language if self.state.language in PROMPTS.get(key, {}) else "English"
        template = PROMPTS[key][language]
        return template.format(**kwargs)

    async def _generate_research_plan(self):
        logger.info(f"Generating research plan for topic: {self.state.research_topic} (Language: {self.state.language})")
        if self.progress_callback: await self.progress_callback("Generating structured research plan...")

        try:
            min_sec = getattr(self.config, "RESEARCH_PLAN_MIN_SECTIONS", 3)
            max_sec = getattr(self.config, "RESEARCH_PLAN_MAX_SECTIONS", 5)

            prompt = self._get_prompt(
                "generate_research_plan",
                min_sec=min_sec,
                max_sec=max_sec,
                topic=self.state.research_topic
            )

            plan_model = await self.llm_client.generate_structured(prompt=prompt, response_model=ResearchPlanModel)

            self.state.research_plan = []
            for sec in plan_model.sections:
                self.state.research_plan.append({
                    "title": sec.title,
                    "description": sec.description,
                    "status": "pending",
                    "summary": "",
                    "sources": []
                })

            self.state.current_section_index = -1
            
            # Visibility Enhancement: Emit plan details as formatted message
            plan_str = "## 📋 Research Plan\n\n"
            for i, sec in enumerate(self.state.research_plan):
                plan_str += f"{i+1}. **{sec['title']}**\n   - {sec['description']}\n\n"
            if self.progress_callback: 
                await self.progress_callback(plan_str)
            
            logger.info(f"Research plan generated with {len(self.state.research_plan)} sections.")
        except Exception as e:
            logger.error(f"Error generating research plan: {e}", exc_info=True)
            self.state.research_plan = [{"title": "General Research", "description": f"Research on {self.state.research_topic}", "status": "pending", "summary": "", "sources": []}]
            self.state.current_section_index = -1

    def _get_current_section(self):
        if 0 <= self.state.current_section_index < len(self.state.research_plan):
            return self.state.research_plan[self.state.current_section_index]
        return None

    async def _generate_initial_query(self):
        section = self._get_current_section()
        topic = section['title'] if section else self.state.research_topic
        desc = section['description'] if section else ""

        logger.info(f"Generating initial query for: {topic}")
        try:
            max_words = getattr(self.config, "MAX_QUERY_WORDS", 12)
            prompt = self._get_prompt(
                "generate_initial_query",
                max_words=max_words,
                topic=self.state.research_topic,
                section_topic=topic,
                description=desc
            )
            query = await self.llm_client.generate_text(prompt=prompt)
            self.state.proposed_query = query
            self.state.current_query = None
        except Exception as e:
            logger.error(f"Error generating query: {e}")
            self.state.proposed_query = None

    async def _web_search(self):
        if not self.state.current_query: return
        logger.info(f"Performing web search for: {self.state.current_query}")
        if self.progress_callback: await self.progress_callback(f"Searching web for: '{self.state.current_query}'...")
        try:
            results = await self.search_client.search(self.state.current_query, num_results=self.config.MAX_SEARCH_RESULTS_PER_QUERY)
            self.state.search_results = results
            self.state.pending_source_selection = bool(results)
            if self.progress_callback:
                if results:
                    results_str = "\n".join([f"- [{r['title']}]({r['link']})" for r in results])
                    await self.progress_callback(f"Found {len(results)} potential sources:\n{results_str}")
                else:
                    await self.progress_callback("No search results found.")
        except Exception as e:
            logger.error(f"Error during search: {e}")
            self.state.search_results = []
            self.state.pending_source_selection = False
            if self.progress_callback: await self.progress_callback(f"Search failed: {e}")

    async def _summarize_sources(self, selected_results: List[SearchResult]):
        if not selected_results:
            self.state.new_information = "No sources selected."
            self.state.pending_source_selection = False
            return

        if self.progress_callback:
             sources_titles = ", ".join([r['title'] for r in selected_results])
             await self.progress_callback(f"Summarizing {len(selected_results)} sources: {sources_titles}...")

        all_chunk_summaries = []
        all_chunks_info = [] # Store all chunks to be processed in parallel
        if self.state.fetched_content is None: self.state.fetched_content = {}

        for result in selected_results:
            url = result['link']
            if url not in self.state.fetched_content:
                if self.config.USE_SNIPPETS_ONLY_MODE:
                    content = result.get('snippet', '')
                else:
                    content = await self.content_retriever.retrieve_and_extract(url)
                    if not content: content = result.get('snippet', '')
                self.state.fetched_content[url] = content

            content = self.state.fetched_content[url]
            chunks = split_text_into_chunks(content, self.config.SUMMARIZATION_CHUNK_SIZE_CHARS, self.config.SUMMARIZATION_CHUNK_OVERLAP_CHARS)
            all_chunks_info.extend([(chunk, url) for chunk in chunks])

        # Limit concurrency using Semaphore
        semaphore = asyncio.Semaphore(self.config.MAX_CONCURRENT_CHUNKS)

        async def summarize_chunk(chunk_info):
            chunk, url = chunk_info
            if self.state.is_interrupted: return None
            async with semaphore:
                if self.progress_callback: await self.progress_callback(f"Summarizing chunk from {url}...")
                prompt = self._get_prompt(
                    "summarize_chunk",
                    query=self.state.current_query,
                    chunk=chunk
                )
                return await self.llm_client.generate_text(prompt=prompt)

        # Execute parallel summarization
        if all_chunks_info:
            if self.progress_callback: await self.progress_callback(f"Starting parallel summarization for {len(all_chunks_info)} chunks...")
            summaries = await asyncio.gather(*[summarize_chunk(info) for info in all_chunks_info])
            all_chunk_summaries.extend([s for s in summaries if s])
        
        if self.state.is_interrupted:
             return

        if not all_chunk_summaries:
            self.state.new_information = "Could not summarize any content."
            if self.progress_callback: await self.progress_callback("No content could be summarized.")
        else:
            if self.progress_callback: await self.progress_callback("Synthesizing final summary for the query...")
            combined = "\n\n---\n\n".join(all_chunk_summaries)
            prompt = self._get_prompt(
                "combine_summaries",
                query=self.state.current_query,
                summaries=combined
            )
            self.state.new_information = await self.llm_client.generate_text(prompt=prompt)
            self.state.accumulated_summary += f"\n\n## {self.state.current_query}\n{self.state.new_information}"
            if self.progress_callback: await self.progress_callback("Summary update complete.")

        for res in selected_results:
            if res['link'] not in [s['link'] for s in self.state.sources_gathered]:
                self.state.sources_gathered.append(Source(title=res['title'], link=res['link']))

        self.state.pending_source_selection = False
        # await self._extract_entities_and_relations() # Now handled in parallel with reflection

    async def _extract_entities_and_relations(self):
        if not self.state.new_information or len(self.state.new_information) < 20: return

        logger.info("Extracting entities and relations (structured).")
        if self.progress_callback: await self.progress_callback("Extracting entities and relations for knowledge graph...")
        prompt = self._get_prompt(
            "extract_entities",
            text=self.state.new_information
        )

        try:
            kg_model = await self.llm_client.generate_structured(prompt=prompt, response_model=KnowledgeGraphModel)

            # Merge nodes
            existing_node_ids = {n['id'] for n in self.state.knowledge_graph_nodes}
            for n in kg_model.nodes:
                if n.id not in existing_node_ids:
                    self.state.knowledge_graph_nodes.append(n.model_dump())
                    existing_node_ids.add(n.id)

            # Merge edges (simplified deduplication based on source/target/label)
            existing_edge_keys = {(e['source'], e['target'], e.get('label')) for e in self.state.knowledge_graph_edges}
            for e in kg_model.edges:
                edge_key = (e.source, e.target, e.label)
                if edge_key not in existing_edge_keys:
                    self.state.knowledge_graph_edges.append(e.model_dump())
                    existing_edge_keys.add(edge_key)

            if self.progress_callback: await self.progress_callback(f"Knowledge graph now has {len(self.state.knowledge_graph_nodes)} nodes and {len(self.state.knowledge_graph_edges)} edges.")
        except Exception as e:
            logger.error(f"KG extraction failed: {e}")
            if self.progress_callback: await self.progress_callback("Knowledge graph extraction skipped or failed.")

    async def _reflect_on_summary(self):
        section = self._get_current_section()
        title = section['title'] if section else "General"

        if self.progress_callback: await self.progress_callback(f"Reflecting on findings for section: '{title}'...")
        prompt = self._get_prompt(
            "reflect_on_summary",
            topic=self.state.research_topic,
            section_title=title,
            summary=self.state.accumulated_summary
        )

        response = await self.llm_client.generate_text(prompt=prompt)
        # Simple parsing for reflection
        lines = response.split('\n')
        evaluation = "CONCLUDE"
        next_query = None
        for line in lines:
            if "EVALUATION:" in line.upper(): evaluation = line.split(":")[-1].strip().upper()
            if "QUERY:" in line.upper():
                q = line.split(":")[-1].strip()
                if q.lower() != "none": next_query = q

        if "CONCLUDE" in evaluation:
            self.state.proposed_query = None
        else:
            self.state.proposed_query = next_query

    async def _finalize_summary(self):
        logger.info("Finalizing report with citations.")

        full_context = ""
        all_sources = []
        if self.state.research_plan:
            for i, sec in enumerate(self.state.research_plan):
                if sec['summary']:
                    full_context += f"\n\n### {sec['title']}\n{sec['summary']}"
                for s in sec['sources']:
                    if s['link'] not in [src['link'] for src in all_sources]:
                        all_sources.append(s)

        source_list_str = "\n".join([f"[{i+1}] {s['title']} ({s['link']})" for i, s in enumerate(all_sources)])

        if not source_list_str:
            source_info = "No specific web sources were found or selected for this research."
            citation_instruction = "Since no sources are available, do not use in-text citations."
        else:
            source_info = f"Reference Sources:\n{source_list_str}"
            citation_instruction = self._get_prompt("citation_instruction")

        prompt = self._get_prompt(
            "finalize_summary",
            topic=self.state.research_topic,
            context=full_context,
            source_info=source_info,
            citation_instruction=citation_instruction
        )

        if self.progress_callback: await self.progress_callback("Synthesizing final research report with all findings...")
        report = await self.llm_client.generate_text(prompt=prompt)

        sources_section = f"\n\n## Sources\n{source_list_str}" if source_list_str else ""
        self.state.final_report = f"{report}{sources_section}"
        if self.progress_callback: await self.progress_callback("Final report generation complete.")

    def format_follow_up_prompt(self, final_report: str, question: str) -> str:
        """Formats the prompt for a follow-up question based on the final report."""
        return self._get_prompt(
            "follow_up_prompt",
            report=final_report,
            question=question
        )

    async def _process_section(self, section):
        """Processes a single research section."""
        section['status'] = 'researching'
        if self.progress_callback: await self.progress_callback(f"Starting research for section: '{section['title']}'")

        if not self.state.current_query and not self.state.proposed_query and self.state.completed_loops == 0:
            await self._generate_initial_query()

        while self.state.completed_loops < self.config.MAX_RESEARCH_LOOPS:
            if self.state.is_interrupted: break

            # Step 1: Ensure we have a current query if needed
            if not self.state.current_query:
                if not self.interactive_mode and self.state.proposed_query:
                    self.state.current_query = self.state.proposed_query
                    self.state.proposed_query = None
                elif self.interactive_mode and self.state.proposed_query:
                    return False # Need interactive input
                else: break

            # Step 2: Search if needed
            if not self.state.pending_source_selection and self.state.search_results is None:
                await self._web_search()

            # Step 3: Summarize if needed
            if self.state.pending_source_selection:
                if not self.interactive_mode:
                    await self._summarize_sources(self.state.search_results or [])
                else: return False # Need interactive input

            # Step 4: After summarization, increment and reflect
            if not self.state.pending_source_selection:
                self.state.completed_loops += 1
                self.state.current_query = None # Clear current query as it's finished
                self.state.search_results = None # Clear results for this query

                if self.state.completed_loops < self.config.MAX_RESEARCH_LOOPS:
                    # Parallelize Graph Extraction and Reflection
                    await asyncio.gather(
                        self._extract_entities_and_relations(),
                        self._reflect_on_summary()
                    )
                    
                    if not self.state.proposed_query: break
                    if not self.interactive_mode:
                        self.state.current_query = self.state.proposed_query
                        self.state.proposed_query = None
                    else: return False # Need interactive input

        section['status'] = 'completed'
        section['summary'] = self.state.accumulated_summary
        section['sources'] = self.state.sources_gathered.copy()

        # Reset section-specific state
        self.state.accumulated_summary = ""
        self.state.sources_gathered = []
        self.state.completed_loops = 0
        self.state.current_query = None
        self.state.proposed_query = None
        self.state.search_results = None
        self.state.fetched_content = {}
        return True

    async def run_loop(self):
        if not self.state.research_plan: await self._generate_research_plan()
        if self.interactive_mode and not self.state.plan_approved: return

        if self.state.current_section_index == -1: self.state.current_section_index = 0

        while self.state.current_section_index < len(self.state.research_plan):
            if self.state.is_interrupted:
                logger.info("Research interrupted by user.")
                if self.progress_callback: await self.progress_callback("Research interrupted by user. Finalizing report with current findings...")
                break

            section = self.state.research_plan[self.state.current_section_index]
            if section['status'] == 'completed':
                self.state.current_section_index += 1
                continue

            success = await self._process_section(section)
            if not success and self.interactive_mode:
                return None # Wait for interactive input

            self.state.current_section_index += 1

        await self._finalize_summary()
        return self.state.final_report
