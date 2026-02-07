from deep_research_project.config.config import Configuration
from .state import (
    ResearchState, SearchResult, Source,
    ResearchPlanModel, KnowledgeGraphModel
)

from deep_research_project.tools.llm_client import LLMClient
from deep_research_project.tools.search_client import SearchClient
from deep_research_project.tools.content_retriever import ContentRetriever
from deep_research_project.core.planning import PlanGenerator
from deep_research_project.core.execution import ExecutionManager
from deep_research_project.core.reflection import ReflectionManager
from deep_research_project.core.reporting import ReportGenerator

import logging
import json
import asyncio
from typing import List, Optional, Callable

logger = logging.getLogger(__name__)


class ResearchLoop:
    def __init__(self, config: Configuration, state: ResearchState, progress_callback: Optional[Callable[[str], None]] = None):
        self.config = config
        self.state = state
        self.interactive_mode = config.INTERACTIVE_MODE
        self.progress_callback = progress_callback

        self.llm_client = LLMClient(config)
        self.search_client = SearchClient(config)
        self.content_retriever = ContentRetriever(config=self.config, progress_callback=progress_callback)

        self.planner = PlanGenerator(self.llm_client, config)
        self.executor = ExecutionManager(self.llm_client, self.search_client, self.content_retriever, config)
        self.reflector = ReflectionManager(self.llm_client, config)
        self.reporter = ReportGenerator(self.llm_client, config)

    async def _generate_research_plan(self):
        self.state.research_plan = await self.planner.generate_plan(
            self.state.research_topic,
            self.state.language,
            self.progress_callback
        )
        self.state.current_section_index = -1

    def _get_current_section(self):
        if 0 <= self.state.current_section_index < len(self.state.research_plan):
            return self.state.research_plan[self.state.current_section_index]
        return None

    async def _generate_initial_query(self):
        section = self._get_current_section()
        topic = section['title'] if section else self.state.research_topic
        desc = section['description'] if section else ""

        query = await self.executor.generate_initial_query(self.state, topic, desc)
        self.state.proposed_query = query
        self.state.current_query = None

    async def _web_search(self):
        if not self.state.current_query: return
        results = await self.executor.web_search(self.state.current_query, self.progress_callback)
        self.state.search_results = results
        self.state.pending_source_selection = bool(results)

    async def _summarize_sources(self, selected_results: List[SearchResult]):
        await self.executor.summarize_sources(self.state, selected_results, self.progress_callback)

    async def _extract_entities_and_relations(self):
        await self.executor.extract_entities_and_relations(self.state, self.progress_callback)

    async def _reflect_on_summary(self):
        section = self._get_current_section()
        title = section['title'] if section else "General"

        next_query, evaluation = await self.reflector.reflect_on_summary(
            self.state.research_topic,
            title,
            self.state.accumulated_summary,
            self.state.language,
            self.progress_callback
        )

        if "CONCLUDE" in evaluation:
            self.state.proposed_query = None
        else:
            self.state.proposed_query = next_query

    async def _finalize_summary(self):
        self.state.final_report = await self.reporter.finalize_report(
            self.state.research_topic,
            self.state.research_plan,
            self.state.language,
            self.progress_callback
        )

    def format_follow_up_prompt(self, final_report: str, question: str) -> str:
        return self.reporter.format_follow_up_prompt(final_report, question, self.state.language)

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
