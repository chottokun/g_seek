import asyncio
import logging
from typing import List, Dict, Optional, Any, Callable

from deep_research_project.config.config import Configuration
from deep_research_project.core.state import ResearchState, Source, SearchResult
from deep_research_project.tools.llm_client import LLMClient
from deep_research_project.tools.search_client import SearchClient
from deep_research_project.tools.content_retriever import ContentRetriever

# New modular components
from deep_research_project.core.planning import ResearchPlanner
from deep_research_project.core.execution import ResearchExecutor
from deep_research_project.core.reflection import ResearchReflector
from deep_research_project.core.reporting import ResearchReporter
from deep_research_project.core.prompts import (
    NO_INFO_FOUND_MSG_JA, NO_INFO_FOUND_MSG_EN,
    FOLLOW_UP_PROMPT_JA, FOLLOW_UP_PROMPT_EN
)

logger = logging.getLogger(__name__)


class ResearchLoop:
    def __init__(self, config: Configuration, state: ResearchState, progress_callback: Optional[Callable[[str], Any]] = None):
        self.config = config
        self.state = state
        self.progress_callback = progress_callback
        self.interactive_mode = getattr(config, "INTERACTIVE_MODE", False)

        # Clients
        self.llm_client = LLMClient(config)
        self.search_client = SearchClient(config)
        self.content_retriever = ContentRetriever(config=self.config, progress_callback=progress_callback)

        # Modular components (SRP)
        self.planner = ResearchPlanner(config, self.llm_client)
        self.executor = ResearchExecutor(config, self.llm_client, self.search_client, self.content_retriever)
        self.reflector = ResearchReflector(config, self.llm_client)
        self.reporter = ResearchReporter(self.llm_client)

    async def _generate_research_plan(self):
        """Delegates research plan generation to the planner module."""
        callback = self.progress_callback
        self.state.research_plan = await self.planner.generate_plan(
            self.state.research_topic, self.state.language, callback
        )
        if callback: 
            await callback(f"Research plan generated with {len(self.state.research_plan)} sections.")

    def _get_current_section(self):
        if 0 <= self.state.current_section_index < len(self.state.research_plan):
            return self.state.research_plan[self.state.current_section_index]
        return None

    async def _generate_initial_query(self):
        """Delegates initial query generation to the planner module."""
        current_section = self._get_current_section()
        if not current_section:
            # Fallback if no section is available
            topic = self.state.research_topic
            section_title = "General"
            section_description = f"Research on {topic}"
        else:
            topic = self.state.research_topic
            section_title = current_section['title']
            section_description = current_section.get('description', section_title)
        
        callback = self.progress_callback
        self.state.current_query = await self.planner.generate_initial_query(
            topic=topic,
            section_title=section_title,
            section_description=section_description,
            language=self.state.language,
            progress_callback=callback
        )
        if callback: 
            await callback(f"Initial query: {self.state.current_query}")

    async def _web_search(self, callback_override=None):
        """Delegates web search to the execution module with relevance filtering."""
        if not self.state.current_query: return
        
        # Perform initial search
        results = await self.executor.search(
            self.state.current_query, getattr(self.config, "MAX_SEARCH_RESULTS_PER_QUERY", 3)
        )
        
        # Apply relevance filtering if enabled
        enable_rel = getattr(self.config, "ENABLE_RELEVANCE_FILTERING", True)
        rel_mode = getattr(self.config, "RELEVANCE_FILTER_MODE", "snippet")
        
        if enable_rel and rel_mode != "disabled":
            if rel_mode == "snippet":
                # Mode A: Snippet-based pre-filtering (default, recommended)
                results = await self.executor.filter_by_relevance(
                    self.state.current_query, results, self.state.language, use_snippet=True
                )
                logger.info(f"Pre-filtered to {len(results)} relevant results (snippet-based)")
                
                # Zero-result fallback strategy with infinite loop prevention
                if len(results) == 0 and getattr(self.config, "ENABLE_QUERY_REGENERATION", True):
                    logger.warning(f"No relevant results found for query: '{self.state.current_query}'. Applying fallback strategy...")
                    
                    # Check if query was already regenerated (infinite loop prevention)
                    if self.state.current_query not in self.state.regenerated_queries:
                        # Stage 1: Query regeneration (max 1 time)
                        current_section = self._get_current_section()
                        section_title = current_section['title'] if current_section else "General"
                        
                        new_query = await self.planner.regenerate_query(
                            original_query=self.state.current_query,
                            topic=self.state.research_topic,
                            section_title=section_title,
                            language=self.state.language
                        )
                        logger.info(f"Regenerated query: '{new_query}'")
                        
                        # Track regenerated queries to prevent infinite loops
                        self.state.regenerated_queries.add(self.state.current_query)
                        self.state.regenerated_queries.add(new_query)
                        
                        # Re-search with new query
                        results = await self.executor.search(new_query, getattr(self.config, "MAX_SEARCH_RESULTS_PER_QUERY", 3))
                        results = await self.executor.filter_by_relevance(
                            new_query, results, self.state.language, use_snippet=True
                        )
                        logger.info(f"Re-filtered to {len(results)} relevant results with new query")
                        
                        # Update current query to the regenerated one
                        self.state.current_query = new_query
                    else:
                        logger.warning(f"Query '{self.state.current_query}' already regenerated. Skipping to fallback.")
                    
                    # Stage 2: Lowered threshold fallback
                    if len(results) == 0:
                        logger.warning("Still no relevant results after query regeneration. Lowering threshold...")
                        results = await self.executor.search(self.state.current_query, self.config.MAX_SEARCH_RESULTS_PER_QUERY)
                        results = await self.executor.filter_by_relevance(
                            self.state.current_query, results, self.state.language, use_snippet=True,
                            threshold=getattr(self.config, "RELEVANCE_THRESHOLD", 0.6) * 0.5  # Lower threshold by 50%
                        )
                        logger.info(f"Fallback: Filtered to {len(results)} results with lowered threshold")
                    
                    # Stage 3: Mark as "no results found" (do NOT use unfiltered results)
                    if len(results) == 0:
                        logger.warning(f"No relevant results found for query '{self.state.current_query}' even with lowered threshold. Marking as 'no results found'.")
                        # Empty results list will be handled downstream
                        # The summarization step will generate a "no information found" message
            
            elif rel_mode == "full_content":
                # Mode B: Full-content-based filtering (not implemented in this phase)
                # Would require retrieving full content first, then filtering
                # For now, fall back to snippet mode
                logger.warning("RELEVANCE_FILTER_MODE='full_content' not yet implemented. Falling back to snippet mode.")
                results = await self.executor.filter_by_relevance(
                    self.state.current_query, results, self.state.language, use_snippet=True
                )
        
        self.state.search_results = results
        self.state.pending_source_selection = True
        
        callback = self.progress_callback
        if callback:
            await callback(f"Found {len(results)} relevant results.")

    async def _summarize_sources(self, selected_results: List[SearchResult], callback_override=None):
        """Delegates retrieval and summarization to the execution module."""
        # Handle empty results (from relevance filtering)
        if not selected_results:
            if self.state.language == "Japanese":
                self.state.new_information = NO_INFO_FOUND_MSG_JA.format(query=self.state.current_query)
            else:
                self.state.new_information = NO_INFO_FOUND_MSG_EN.format(query=self.state.current_query)
            
            logger.info(f"No results to summarize for query: '{self.state.current_query}'")
            self.state.pending_source_selection = False
            return
        
        callback = self.progress_callback
        self.state.new_information = await self.executor.retrieve_and_summarize(
            selected_results, self.state.current_query, self.state.language,
            self.state.fetched_content, callback
        )
        
        if self.state.new_information:
            self.state.accumulated_summary.append(f"\n\n## {self.state.current_query}\n{self.state.new_information}")
        
        # Add new sources to gathered list (O(N) source deduplication)

        gathered_links = {s.link for s in self.state.sources_gathered}
        for res in selected_results:
            if res.link not in gathered_links:
                self.state.sources_gathered.append(Source(title=res.title, link=res.link))
                gathered_links.add(res.link)
        
        self.state.pending_source_selection = False

    async def _extract_entities_and_relations(self, callback_override=None):
        """Delegates KG extraction and merging to the reflection module."""
        current_section = self._get_current_section()
        section_title = current_section['title'] if current_section else "General"
        
        await self.reflector.extract_knowledge_graph(
            self.state.new_information, self.state.sources_gathered,
            section_title, self.state.language,
            self.state.knowledge_graph_nodes, self.state.knowledge_graph_edges
        )
        
        callback = self.progress_callback
        if callback: 
            await callback(f"Knowledge graph enhanced: {len(self.state.knowledge_graph_nodes)} nodes, {len(self.state.knowledge_graph_edges)} edges.")

    async def _reflect_on_summary(self):
        """Delegates reflection and decision making to the reflection module."""
        section = self._get_current_section()
        if not section:
            title = "General"
            description = f"Research on {self.state.research_topic}"
        else:
            title = section['title']
            description = section.get('description', title)

        evaluation, next_query = await self.reflector.reflect_and_decide(
            topic=self.state.research_topic,
            section_title=title,
            section_description=description,
            accumulated_summary="".join(self.state.accumulated_summary),
            language=self.state.language
        )

        if "CONCLUDE" in evaluation:
            self.state.proposed_query = None
        else:
            self.state.proposed_query = next_query

    async def _finalize_summary(self):
        """Delegates final report synthesis to the reporting module."""
        callback = self.progress_callback
        if callback: await callback("Synthesizing final research report...")
        
        # Extract findings and sources from the completed research plan
        findings = []
        sources = []
        for section in self.state.research_plan:
            if section.get('summary'):
                findings.append(section['summary'])
            if section.get('sources'):
                sources.extend(section['sources'])

        self.state.final_report = await self.reporter.finalize_report(
            self.state.research_topic, findings, sources, self.state.language
        )
        if callback: await callback("Final report generation complete.")

    def format_follow_up_prompt(self, final_report: str, question: str) -> str:
        """Formats the prompt for a follow-up question based on the final report."""
        if self.state.language == "Japanese":
            return FOLLOW_UP_PROMPT_JA.format(
                final_report=final_report,
                question=question
            )
        else:
            return FOLLOW_UP_PROMPT_EN.format(
                final_report=final_report,
                question=question
            )

    async def _process_section(self, section, callback_override=None):
        """Processes a single research section and returns results."""
        section_findings = []
        section_sources = []
        
        callback = callback_override or self.progress_callback
        if callback: await callback(f"Starting research for section: '{section['title']}'")

        # Step 1: Initial Query
        current_query = await self.planner.generate_initial_query(
            topic=self.state.research_topic,
            section_title=section['title'],
            section_description=section.get('description', section['title']),
            language=self.state.language,
            progress_callback=callback
        )
        if callback: await callback(f"[{section['title']}] Initial query: {current_query}")
        
        for loop_idx in range(getattr(self.config, "MAX_RESEARCH_LOOPS", 5)):
            if self.state.is_interrupted: break
            
            # Step 2: Search
            results = await self.executor.search(current_query, getattr(self.config, "MAX_SEARCH_RESULTS_PER_QUERY", 3))
            
            # Step 3: Filter and Summarize
            relevant = await self.executor.filter_by_relevance(current_query, results, self.state.language)
            if callback: await callback(f"[{section['title']}] Found {len(relevant)} relevant results.")
            
            if not relevant:
                if callback: await callback(f"[{section['title']}] No relevant information found.")
                break
                
            summary = await self.executor.retrieve_and_summarize(
                relevant, current_query, self.state.language, {}, callback
            )
            
            if summary:
                section_findings.append(summary)
                for r in relevant:
                    section_sources.append(Source(title=r.title, link=r.link))
            
            # Step 4: Reflect & Decide loop continuation
            reflection = await self.reflector.reflect(
                topic=self.state.research_topic,
                section_title=section['title'],
                section_description=section.get('description', ''),
                accumulated_summary="\n\n".join(section_findings),
                language=self.state.language
            )
            
            evaluation = reflection.get("evaluation", "CONCLUDE")
            next_query = reflection.get("query")
            
            if evaluation == "CONTINUE" and next_query and next_query.lower() != "none":
                current_query = next_query
                if callback: await callback(f"[{section['title']}] Continuing with new query: {current_query}")
            else:
                break

        # Finalize section state
        section['status'] = 'completed'
        section['summary'] = "\n\n".join(section_findings)
        section['sources'] = [s.dict() if hasattr(s, 'dict') else s for s in section_sources]
        
        if callback: await callback(f"[{section['title']}] Section research complete.")
        return True

    async def run_loop(self):
        if not self.state.research_plan: await self._generate_research_plan()
        if self.interactive_mode and not self.state.plan_approved: return
        
        # In non-interactive mode, we can process all incomplete sections in parallel
        if not self.interactive_mode:
            incomplete_sections = [s for s in self.state.research_plan if s['status'] != 'completed']
            if incomplete_sections:
                if self.progress_callback:
                    await self.progress_callback(f"🚀 Processing {len(incomplete_sections)} sections in parallel (max {getattr(self.config, 'MAX_CONCURRENT_SECTIONS', 3)} at once)...")
                
                # Instance-level semaphore to control concurrency within this loop
                max_sections = getattr(self.config, "MAX_CONCURRENT_SECTIONS", 3)
                section_semaphore = asyncio.Semaphore(max_sections)

                # Wrap progress callback to include section title context
                async def run_section_with_context(sec):
                    async with section_semaphore: # Control parallel execution
                        orig_callback = self.progress_callback
                        if orig_callback:
                            async def wrapped_callback(msg):
                                await orig_callback(f"[{sec['title']}] {msg}")
                            return await self._process_section(sec, callback_override=wrapped_callback)
                        else:
                            return await self._process_section(sec)

                # Execute all sections concurrently, but limited by the semaphore
                await asyncio.gather(*[run_section_with_context(s) for s in incomplete_sections])
        else:
            # Sequential processing for interactive mode to allow per-step approval
            if self.state.current_section_index == -1: self.state.current_section_index = 0
            while self.state.current_section_index < len(self.state.research_plan):
                if self.state.is_interrupted:
                    logger.info("Research interrupted by user.")
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
