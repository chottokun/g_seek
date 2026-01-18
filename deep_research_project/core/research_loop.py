from deep_research_project.config.config import Configuration
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

    async def _generate_research_plan(self):
        logger.info(f"Generating research plan for topic: {self.state.research_topic}")
        if self.progress_callback: self.progress_callback("Generating structured research plan...")

        try:
            prompt = (
                f"Based on the following research topic, generate a structured research plan consisting of 3 to 5 key sections.\n"
                f"Research Topic: {self.state.research_topic}\n\n"
                f"For each section, provide a title and a brief description of what should be researched."
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
            prompt = (
                f"Generate a concise web search query (max 12 words) for the following research task.\n"
                f"Main Topic: {self.state.research_topic}\n"
                f"Section: {topic}\n"
                f"Description: {desc}\n\n"
                f"Output only the query."
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
        if self.progress_callback: self.progress_callback(f"Searching web for: '{self.state.current_query}'...")
        try:
            results = await self.search_client.search(self.state.current_query, num_results=self.config.MAX_SEARCH_RESULTS_PER_QUERY)
            self.state.search_results = results
            self.state.pending_source_selection = bool(results)
            if self.progress_callback:
                if results:
                    self.progress_callback(f"Found {len(results)} potential sources.")
                else:
                    self.progress_callback("No search results found.")
        except Exception as e:
            logger.error(f"Error during search: {e}")
            self.state.search_results = []
            self.state.pending_source_selection = False
            if self.progress_callback: self.progress_callback(f"Search failed: {e}")

    async def _summarize_sources(self, selected_results: List[SearchResult]):
        if not selected_results:
            self.state.new_information = "No sources selected."
            self.state.pending_source_selection = False
            return

        if self.progress_callback: self.progress_callback(f"Summarizing {len(selected_results)} sources...")

        all_chunk_summaries = []
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

            for i, chunk in enumerate(chunks):
                if self.progress_callback: self.progress_callback(f"Summarizing chunk {i+1}/{len(chunks)} from {url}...")
                prompt = f"Summarize this segment for the research query: '{self.state.current_query}'.\n\nSegment:\n{chunk}"
                summary = await self.llm_client.generate_text(prompt=prompt)
                if summary: all_chunk_summaries.append(summary)

        if not all_chunk_summaries:
            self.state.new_information = "Could not summarize any content."
            if self.progress_callback: self.progress_callback("No content could be summarized.")
        else:
            if self.progress_callback: self.progress_callback("Synthesizing final summary for the query...")
            combined = "\n\n---\n\n".join(all_chunk_summaries)
            prompt = f"Combine these summaries into one coherent summary for query: '{self.state.current_query}'.\n\nSummaries:\n{combined}"
            self.state.new_information = await self.llm_client.generate_text(prompt=prompt)
            self.state.accumulated_summary += f"\n\n## {self.state.current_query}\n{self.state.new_information}"
            if self.progress_callback: self.progress_callback("Summary update complete.")

        for res in selected_results:
            if res['link'] not in [s['link'] for s in self.state.sources_gathered]:
                self.state.sources_gathered.append(Source(title=res['title'], link=res['link']))

        self.state.pending_source_selection = False
        await self._extract_entities_and_relations()

    async def _extract_entities_and_relations(self):
        if not self.state.new_information or len(self.state.new_information) < 20: return

        logger.info("Extracting entities and relations (structured).")
        if self.progress_callback: self.progress_callback("Extracting entities and relations for knowledge graph...")
        prompt = f"Identify key entities and relationships from this text:\n\n{self.state.new_information}"

        try:
            kg_model = await self.llm_client.generate_structured(prompt=prompt, response_model=KnowledgeGraphModel)
            self.state.knowledge_graph_nodes = [n.model_dump() for n in kg_model.nodes]
            self.state.knowledge_graph_edges = [e.model_dump() for e in kg_model.edges]
            if self.progress_callback: self.progress_callback(f"Extracted {len(self.state.knowledge_graph_nodes)} nodes and {len(self.state.knowledge_graph_edges)} edges.")
        except Exception as e:
            logger.error(f"KG extraction failed: {e}")
            if self.progress_callback: self.progress_callback("Knowledge graph extraction skipped or failed.")

    async def _reflect_on_summary(self):
        section = self._get_current_section()
        title = section['title'] if section else "General"

        if self.progress_callback: self.progress_callback(f"Reflecting on findings for section: '{title}'...")
        prompt = (
            f"Topic: {self.state.research_topic}\n"
            f"Section: {title}\n"
            f"Current Summary:\n{self.state.accumulated_summary}\n\n"
            f"Evaluate if more research is needed for this section. "
            f"Format: EVALUATION: <CONTINUE|CONCLUDE>\nQUERY: <Next search query or None>"
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

        prompt = (
            f"Synthesize a final research report for the topic: {self.state.research_topic}\n\n"
            f"Research Context (Summaries from various sections):\n{full_context}\n\n"
            f"Reference Sources:\n{source_list_str}\n\n"
            f"STRICT INSTRUCTIONS:\n"
            f"1. The report must be comprehensive, professional, and well-structured with clear headings.\n"
            f"2. You MUST use numbered in-text citations such as [1] or [2, 3] to attribute information to the sources listed above.\n"
            f"3. Every major claim or data point should ideally be cited.\n"
            f"4. Do not mention sources that are not in the provided list.\n"
            f"5. End with a summary of the findings."
        )

        if self.progress_callback: self.progress_callback("Synthesizing final research report with all findings...")
        report = await self.llm_client.generate_text(prompt=prompt)
        self.state.final_report = f"{report}\n\n## Sources\n{source_list_str}"
        if self.progress_callback: self.progress_callback("Final report generation complete.")

    async def run_loop(self):
        if not self.state.research_plan: await self._generate_research_plan()
        if self.interactive_mode and not self.state.plan_approved: return

        if self.state.current_section_index == -1: self.state.current_section_index = 0

        while self.state.current_section_index < len(self.state.research_plan):
            section = self.state.research_plan[self.state.current_section_index]
            if section['status'] == 'completed':
                self.state.current_section_index += 1
                continue

            section['status'] = 'researching'
            if self.progress_callback: self.progress_callback(f"Starting research for section: '{section['title']}'")
            if not self.state.current_query and not self.state.proposed_query and self.state.completed_loops == 0:
                await self._generate_initial_query()

            while self.state.completed_loops < self.config.MAX_RESEARCH_LOOPS:
                if not self.state.current_query:
                    if not self.interactive_mode and self.state.proposed_query:
                        self.state.current_query = self.state.proposed_query
                        self.state.proposed_query = None
                    elif self.interactive_mode and self.state.proposed_query:
                        return
                    else: break

                if not self.state.pending_source_selection:
                    await self._web_search()

                if self.state.pending_source_selection:
                    if not self.interactive_mode:
                        await self._summarize_sources(self.state.search_results or [])
                    else: return

                if not self.state.pending_source_selection:
                    self.state.completed_loops += 1
                    if self.state.completed_loops < self.config.MAX_RESEARCH_LOOPS:
                        await self._reflect_on_summary()
                        if not self.state.proposed_query: break
                        if not self.interactive_mode:
                            self.state.current_query = self.state.proposed_query
                            self.state.proposed_query = None
                        else: return

            section['status'] = 'completed'
            section['summary'] = self.state.accumulated_summary
            section['sources'] = self.state.sources_gathered.copy()

            self.state.accumulated_summary = ""
            self.state.sources_gathered = []
            self.state.completed_loops = 0
            self.state.current_query = None
            self.state.proposed_query = None
            self.state.search_results = None
            self.state.fetched_content = {}
            self.state.current_section_index += 1

        await self._finalize_summary()
        return self.state.final_report
