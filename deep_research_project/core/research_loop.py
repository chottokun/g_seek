import asyncio
import logging
from typing import List, Dict, Optional, Any, Callable

from deep_research_project.config.config import Configuration
from deep_research_project.core.state import ResearchState, Source, SearchResult, SectionPlan
from deep_research_project.tools.llm_client import LLMClient
from deep_research_project.tools.search_client import SearchClient
from deep_research_project.tools.content_retriever import ContentRetriever

# New modular components
from deep_research_project.core.planning import ResearchPlanner
from deep_research_project.core.execution import ResearchExecutor
from deep_research_project.core.reflection import ResearchReflector
from deep_research_project.core.reporting import ResearchReporter

logger = logging.getLogger(__name__)


class ResearchLoop:
    def __init__(self, config: Configuration, state: ResearchState, progress_callback: Optional[Callable[[str], Any]] = None):
        self.config = config
        self.state = state
        self.progress_callback = progress_callback
        self.interactive_mode = config.INTERACTIVE_MODE

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
        self.state.research_plan = await self.planner.generate_plan(
            self.state.research_topic, self.state.language, self.progress_callback
        )
        if self.progress_callback: 
            await self.progress_callback(f"Research plan generated with {len(self.state.research_plan)} sections.")

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
        
        self.state.current_query = await self.planner.generate_initial_query(
            topic=topic,
            section_title=section_title,
            section_description=section_description,
            language=self.state.language,
            progress_callback=self.progress_callback
        )
        if self.progress_callback: 
            await self.progress_callback(f"Initial query: {self.state.current_query}")

    async def _web_search(self):
        """Delegates web search to the execution module with relevance filtering."""
        if not self.state.current_query: return
        
        # Perform initial search
        results = await self.executor.search(
            self.state.current_query, self.config.MAX_SEARCH_RESULTS_PER_QUERY
        )
        
        # Apply relevance filtering if enabled
        if self.config.ENABLE_RELEVANCE_FILTERING and self.config.RELEVANCE_FILTER_MODE != "disabled":
            if self.config.RELEVANCE_FILTER_MODE == "snippet":
                # Mode A: Snippet-based pre-filtering (default, recommended)
                results = await self.executor.filter_by_relevance(
                    self.state.current_query, results, self.state.language, use_snippet=True
                )
                logger.info(f"Pre-filtered to {len(results)} relevant results (snippet-based)")
                
                # Zero-result fallback strategy with infinite loop prevention
                if len(results) == 0 and self.config.ENABLE_QUERY_REGENERATION:
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
                        results = await self.executor.search(new_query, self.config.MAX_SEARCH_RESULTS_PER_QUERY)
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
                            threshold=self.config.RELEVANCE_THRESHOLD * 0.5  # Lower threshold by 50%
                        )
                        logger.info(f"Fallback: Filtered to {len(results)} results with lowered threshold")
                    
                    # Stage 3: Mark as "no results found" (do NOT use unfiltered results)
                    if len(results) == 0:
                        logger.warning(f"No relevant results found for query '{self.state.current_query}' even with lowered threshold. Marking as 'no results found'.")
                        # Empty results list will be handled downstream
                        # The summarization step will generate a "no information found" message
            
            elif self.config.RELEVANCE_FILTER_MODE == "full_content":
                # Mode B: Full-content-based filtering (not implemented in this phase)
                # Would require retrieving full content first, then filtering
                # For now, fall back to snippet mode
                logger.warning("RELEVANCE_FILTER_MODE='full_content' not yet implemented. Falling back to snippet mode.")
                results = await self.executor.filter_by_relevance(
                    self.state.current_query, results, self.state.language, use_snippet=True
                )
        
        self.state.search_results = results
        self.state.pending_source_selection = True
        
        if self.progress_callback:
            await self.progress_callback(f"Found {len(results)} relevant results.")

    async def _summarize_sources(self, selected_results: List[SearchResult]):
        """Delegates retrieval and summarization to the execution module."""
        # Handle empty results (from relevance filtering)
        if not selected_results:
            if self.state.language == "Japanese":
                self.state.new_information = f"クエリ「{self.state.current_query}」に関連する情報が見つかりませんでした。"
            else:
                self.state.new_information = f"No relevant information found for query: '{self.state.current_query}'"
            
            logger.info(f"No results to summarize for query: '{self.state.current_query}'")
            self.state.pending_source_selection = False
            return
        
        self.state.new_information = await self.executor.retrieve_and_summarize(
            selected_results, self.state.current_query, self.state.language,
            self.state.fetched_content, self.progress_callback
        )
        
        if self.state.new_information:
            self.state.accumulated_summary += f"\n\n## {self.state.current_query}\n{self.state.new_information}"
        
        # Add new sources to gathered list
        for res in selected_results:
            if res.link not in [s.link for s in self.state.sources_gathered]:
                self.state.sources_gathered.append(Source(title=res.title, link=res.link))
        
        self.state.pending_source_selection = False

    async def _extract_entities_and_relations(self):
        """Delegates KG extraction and merging to the reflection module."""
        current_section = self._get_current_section()
        section_title = current_section['title'] if current_section else "General"
        
        await self.reflector.extract_knowledge_graph(
            self.state.new_information, self.state.sources_gathered,
            section_title, self.state.language,
            self.state.knowledge_graph_nodes, self.state.knowledge_graph_edges
        )
        
        if self.progress_callback: 
            await self.progress_callback(f"Knowledge graph enhanced: {len(self.state.knowledge_graph_nodes)} nodes, {len(self.state.knowledge_graph_edges)} edges.")

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
            accumulated_summary=self.state.accumulated_summary,
            language=self.state.language
        )

        if "CONCLUDE" in evaluation:
            self.state.proposed_query = None
        else:
            self.state.proposed_query = next_query

    async def _finalize_summary(self):
        """Delegates final report synthesis to the reporting module."""
        if self.progress_callback: await self.progress_callback("Synthesizing final research report...")
        self.state.final_report = await self.reporter.finalize_report(
            self.state.research_topic, self.state.research_plan, self.state.language
        )
        if self.progress_callback: await self.progress_callback("Final report generation complete.")

    def format_follow_up_prompt(self, final_report: str, question: str) -> str:
        """Formats the prompt for a follow-up question based on the final report."""
        if self.state.language == "Japanese":
            return (
                f"以下のリサーチレポートに基づいて、ユーザーのフォローアップ質問に答えてください。\n\n"
                f"レポート:\n{final_report}\n\n"
                f"ユーザーの質問: {question}\n\n"
                f"レポートの内容のみに基づいて、明確で簡潔な回答を提供してください。回答は日本語で行ってください。"
            )
        else:
            return (
                f"Based on the following research report, answer the user's follow-up question.\n\n"
                f"Report:\n{final_report}\n\n"
                f"User Question: {question}\n\n"
                f"Provide a clear and concise answer based only on the report content."
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

                # Parallelize Graph Extraction and Reflection on every loop completion
                await asyncio.gather(
                    self._extract_entities_and_relations(),
                    self._reflect_on_summary()
                )

                if self.state.completed_loops < self.config.MAX_RESEARCH_LOOPS:
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
