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
        logger.info(f"Generating research plan for topic: {self.state.research_topic} (Language: {self.state.language})")
        if self.progress_callback: await self.progress_callback("Generating structured research plan...")

        try:
            if self.state.language == "Japanese":
                prompt = (
                    f"以下のリサーチトピックに基づいて、3〜5つの主要なセクションで構成される構造化されたリサーチ計画を生成してください。\n"
                    f"リサーチトピック: {self.state.research_topic}\n\n"
                    f"各セクションについて、タイトルとリサーチすべき内容の簡潔な説明を提供してください。"
                )
            else:
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
            if self.state.language == "Japanese":
                prompt = (
                    f"以下のリサーチタスクのために、簡潔なWeb検索クエリ（最大12単語）を生成してください。\n"
                    f"メインテーマ: {self.state.research_topic}\n"
                    f"セクション: {topic}\n"
                    f"説明: {desc}\n\n"
                    f"クエリのみを出力してください。英語のソースも取得できるよう、適切であれば英語のクエリも検討してください。"
                )
            else:
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

        async def summarize_chunk(url, chunk, chunk_index, total_chunks):
            if self.state.is_interrupted: return None
            if self.progress_callback: 
                await self.progress_callback(f"Summarizing chunk {chunk_index+1}/{total_chunks} from {url}...")
            
            if self.state.language == "Japanese":
                prompt = f"リサーチクエリ: '{self.state.current_query}' のために、このセグメントを要約してください。\n\nセグメント:\n{chunk}"
            else:
                prompt = f"Summarize this segment for the research query: '{self.state.current_query}'.\n\nSegment:\n{chunk}"
            
            return await self.llm_client.generate_text(prompt=prompt)

        if self.state.fetched_content is None: 
            self.state.fetched_content = {}

        tasks = []
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
                tasks.append(summarize_chunk(url, chunk, i, len(chunks)))

        if tasks:
            summaries = await asyncio.gather(*tasks)
            all_chunk_summaries = [s for s in summaries if s]

        if not all_chunk_summaries:
            self.state.new_information = "Could not summarize any content."
            if self.progress_callback: await self.progress_callback("No content could be summarized.")
        else:
            if self.progress_callback: await self.progress_callback("Synthesizing final summary for the query...")
            combined = "\n\n---\n\n".join(all_chunk_summaries)
            if self.state.language == "Japanese":
                prompt = f"これらの要約を、クエリ: '{self.state.current_query}' に関する一つの首尾一貫した要約にまとめてください。\n\n要約群:\n{combined}"
            else:
                prompt = f"Combine these summaries into one coherent summary for query: '{self.state.current_query}'.\n\nSummaries:\n{combined}"
            self.state.new_information = await self.llm_client.generate_text(prompt=prompt)
            self.state.accumulated_summary += f"\n\n## {self.state.current_query}\n{self.state.new_information}"
            if self.progress_callback: await self.progress_callback("Summary update complete.")

        for res in selected_results:
            if res['link'] not in [s['link'] for s in self.state.sources_gathered]:
                self.state.sources_gathered.append(Source(title=res['title'], link=res['link']))

        self.state.pending_source_selection = False
        await self._extract_entities_and_relations()

    async def _extract_entities_and_relations(self):
        if not self.state.new_information or len(self.state.new_information) < 20: return

        logger.info("Extracting entities and relations (structured).")
        if self.progress_callback: await self.progress_callback("Extracting entities and relations for knowledge graph...")
        if self.state.language == "Japanese":
            prompt = f"このテキストから主要なエンティティと関係を特定してください:\n\n{self.state.new_information}"
        else:
            prompt = f"Identify key entities and relationships from this text:\n\n{self.state.new_information}"

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

    async def _refine_plan(self):
        """Evaluates the research progress and refines the remaining plan."""
        completed_sections = [s for s in self.state.research_plan if s['status'] == 'completed']
        pending_sections = [s for s in self.state.research_plan if s['status'] == 'pending']

        if not pending_sections:
            return

        logger.info("Refining research plan based on current findings.")
        if self.progress_callback: await self.progress_callback("Reviewing research progress to refine the plan...")

        findings_summary = ""
        for s in completed_sections:
            findings_summary += f"\n### {s['title']}\n{s['summary'][:500]}...\n" # Use snippet of summary

        remaining_plan_str = ""
        for i, s in enumerate(pending_sections):
            remaining_plan_str += f"{i+1}. {s['title']}: {s['description']}\n"

        if self.state.language == "Japanese":
            prompt = (
                f"トピック: {self.state.research_topic}\n"
                f"これまでの調査結果（抜粋）:\n{findings_summary}\n"
                f"現在の残りの計画:\n{remaining_plan_str}\n"
                f"これまでの調査結果に基づき、残りのリサーチ計画を最適化してください。"
                f"必要に応じて、セクションの追加、削除、または内容の変更を行ってください。"
                f"すでに完了した調査内容と重複しないように注意してください。"
            )
        else:
            prompt = (
                f"Topic: {self.state.research_topic}\n"
                f"Current Findings (Excerpts):\n{findings_summary}\n"
                f"Current Remaining Plan:\n{remaining_plan_str}\n"
                f"Based on the findings so far, optimize the remaining research plan. "
                f"Add, remove, or modify the remaining sections as necessary to ensure a comprehensive report. "
                f"Avoid duplicating what has already been researched."
            )

        try:
            refined_plan_model = await self.llm_client.generate_structured(prompt=prompt, response_model=ResearchPlanModel)

            # Reconstruct the plan: completed + refined remaining
            new_plan = completed_sections.copy()
            for sec in refined_plan_model.sections:
                new_plan.append({
                    "title": sec.title,
                    "description": sec.description,
                    "status": "pending",
                    "summary": "",
                    "sources": []
                })

            # Check if there's an actual change (basic check on titles)
            old_titles = [s['title'] for s in pending_sections]
            new_titles = [sec.title for sec in refined_plan_model.sections]

            if old_titles != new_titles:
                self.state.research_plan = new_plan
                logger.info("Research plan has been refined.")
                if self.progress_callback:
                    plan_msg = "## 🔄 Refined Research Plan\n\n"
                    for i, sec in enumerate(self.state.research_plan):
                        status = "✅" if sec['status'] == 'completed' else "⏳"
                        plan_msg += f"{i+1}. {status} **{sec['title']}**\n"
                    await self.progress_callback(plan_msg)
            else:
                logger.info("No changes needed to the research plan.")

        except Exception as e:
            logger.error(f"Error refining research plan: {e}")
            if self.progress_callback: await self.progress_callback("Plan refinement skipped due to an error.")

    async def _reflect_on_summary(self):
        section = self._get_current_section()
        title = section['title'] if section else "General"

        if self.progress_callback: await self.progress_callback(f"Reflecting on findings for section: '{title}'...")
        if self.state.language == "Japanese":
            prompt = (
                f"トピック: {self.state.research_topic}\n"
                f"セクション: {title}\n"
                f"現在の要約:\n{self.state.accumulated_summary}\n\n"
                f"このセクションにさらなる調査が必要かどうかを評価してください。"
                f"フォーマット: EVALUATION: <CONTINUE|CONCLUDE>\nQUERY: <次の検索クエリまたは None>"
            )
        else:
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

        if not source_list_str:
            source_info = "No specific web sources were found or selected for this research."
            citation_instruction = "Since no sources are available, do not use in-text citations."
        else:
            source_info = f"Reference Sources:\n{source_list_str}"
            if self.state.language == "Japanese":
                citation_instruction = "上記のソースに情報を帰属させるために、[1]や[2, 3]のような番号付きのインライン引用を必ず使用してください。"
            else:
                citation_instruction = "You MUST use numbered in-text citations such as [1] or [2, 3] to attribute information to the sources listed above."

        if self.state.language == "Japanese":
            prompt = (
                f"トピック: {self.state.research_topic} に関する最終的なリサーチレポートを統合してください。\n\n"
                f"リサーチコンテキスト（各セクションからの要約）:\n{full_context}\n\n"
                f"{source_info}\n\n"
                f"厳格な指示:\n"
                f"1. レポートは包括的でプロフェッショナルであり、明確な見出しを伴う構造になっている必要があります。出力は日本語で作成してください。\n"
                f"2. {citation_instruction}\n"
                f"3. ソースがある場合、すべての主要な主張やデータポイントには引用を付けることが理想的です。\n"
                f"4. 提供されたリストにないソースには言及しないでください。\n"
                f"5. 最後に調査結果のまとめを記述してください。"
            )
        else:
            prompt = (
                f"Synthesize a final research report for the topic: {self.state.research_topic}\n\n"
                f"Research Context (Summaries from various sections):\n{full_context}\n\n"
                f"{source_info}\n\n"
                f"STRICT INSTRUCTIONS:\n"
                f"1. The report must be comprehensive, professional, and well-structured with clear headings.\n"
                f"2. {citation_instruction}\n"
                f"3. Every major claim or data point should ideally be cited if sources are available.\n"
                f"4. Do not mention sources that are not in the provided list.\n"
                f"5. End with a summary of the findings."
            )

        if self.progress_callback: await self.progress_callback("Synthesizing final research report with all findings...")
        report = await self.llm_client.generate_text(prompt=prompt)

        sources_section = f"\n\n## Sources\n{source_list_str}" if source_list_str else ""
        self.state.final_report = f"{report}{sources_section}"
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

                if self.state.completed_loops < self.config.MAX_RESEARCH_LOOPS:
                    await self._reflect_on_summary()
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

            # After a section is completed, refine the remaining plan
            await self._refine_plan()

            self.state.current_section_index += 1

        await self._finalize_summary()
        return self.state.final_report
