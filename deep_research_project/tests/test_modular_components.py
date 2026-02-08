import unittest
import asyncio
from unittest.mock import MagicMock, AsyncMock, patch
from deep_research_project.config.config import Configuration
from deep_research_project.tools.llm_client import LLMClient
from deep_research_project.tools.search_client import SearchClient, SearchResult
from deep_research_project.tools.content_retriever import ContentRetriever
from deep_research_project.core.state import ResearchPlanModel, Section, Source, KnowledgeGraphModel

# Modules to test
from deep_research_project.core.planning import ResearchPlanner
from deep_research_project.core.execution import ResearchExecutor
from deep_research_project.core.reflection import ResearchReflector
from deep_research_project.core.reporting import ResearchReporter

class TestModularComponents(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.config = MagicMock(spec=Configuration)
        self.config.RESEARCH_PLAN_MIN_SECTIONS = 2
        self.config.RESEARCH_PLAN_MAX_SECTIONS = 4
        self.config.MAX_CONCURRENT_CHUNKS = 2
        self.config.SUMMARIZATION_CHUNK_SIZE_CHARS = 100
        self.config.SUMMARIZATION_CHUNK_OVERLAP_CHARS = 10
        self.config.USE_SNIPPETS_ONLY_MODE = False
        
        self.mock_llm = MagicMock(spec=LLMClient)
        self.mock_search = MagicMock(spec=SearchClient)
        self.mock_retriever = MagicMock(spec=ContentRetriever)

    # --- ResearchPlanner Tests ---
    async def test_planner_generate_plan_success(self):
        planner = ResearchPlanner(self.config, self.mock_llm)
        mock_model = ResearchPlanModel(sections=[
            Section(title="T1", description="D1"),
            Section(title="T2", description="D2")
        ])
        self.mock_llm.generate_structured = AsyncMock(return_value=mock_model)
        
        plan = await planner.generate_plan("Topic", "English")
        
        self.assertEqual(len(plan), 2)
        self.assertEqual(plan[0]["title"], "T1")
        self.assertEqual(plan[0]["status"], "pending")

    async def test_planner_generate_plan_fallback(self):
        planner = ResearchPlanner(self.config, self.mock_llm)
        self.mock_llm.generate_structured = AsyncMock(side_effect=Exception("Failed"))
        
        plan = await planner.generate_plan("Topic", "English")
        self.assertEqual(len(plan), 1)
        self.assertEqual(plan[0]["title"], "General Research")

    # --- ResearchExecutor Tests ---
    async def test_executor_search(self):
        executor = ResearchExecutor(self.config, self.mock_llm, self.mock_search, self.mock_retriever)
        mock_results = [SearchResult(title="R1", link="L1", snippet="S1")]
        self.mock_search.search = AsyncMock(return_value=mock_results)
        
        results = await executor.search("query", 5)
        self.assertEqual(results, mock_results)

    async def test_executor_retrieve_and_summarize_parallel(self):
        executor = ResearchExecutor(self.config, self.mock_llm, self.mock_search, self.mock_retriever)
        results = [SearchResult(title="R1", link="L1", snippet="S1")]
        fetched = {}
        
        self.mock_retriever.retrieve_and_extract = AsyncMock(return_value="Extracted content from L1")
        self.mock_llm.generate_text = AsyncMock(side_effect=["Summary of chunk", "Final Combined Summary"])
        
        summary = await executor.retrieve_and_summarize(results, "query", "English", fetched)
        
        self.assertEqual(summary, "Final Combined Summary")
        self.assertIn("L1", fetched)

    # --- ResearchReflector Tests ---
    async def test_reflector_merge_knowledge_graph(self):
        reflector = ResearchReflector(self.config, self.mock_llm)
        existing_nodes = [{"id": "Node1", "label": "L", "properties": {"mention_count": "1"}, "source_urls": ["url1"]}]
        existing_edges = []
        
        new_kg = KnowledgeGraphModel(
            nodes=[
                # Update existing Node1
                {"id": "Node1", "label": "L", "type": "Concept", "properties": {"new_prop": "v"}, "source_urls": ["url2"]},
                # Add new Node2
                {"id": "Node2", "label": "L2", "type": "Person", "properties": {}, "source_urls": ["url1"]}
            ],
            edges=[{"source": "Node1", "target": "Node2", "label": "Related", "properties": {}, "source_urls": []}]
        )
        self.mock_llm.generate_structured = AsyncMock(return_value=new_kg)
        
        await reflector.extract_knowledge_graph("Some text contents for extraction", 
                                              [Source(title="S", link="url1")], 
                                              "Sec1", "English", existing_nodes, existing_edges)
        
        # Check Node1 update
        node1 = next(n for n in existing_nodes if n["id"] == "Node1")
        self.assertEqual(node1["properties"]["mention_count"], "2")
        self.assertEqual(node1["properties"]["new_prop"], "v")
        self.assertIn("url2", node1["source_urls"])
        
        # Check Node2 addition
        self.assertEqual(len(existing_nodes), 2)
        node2 = next(n for n in existing_nodes if n["id"] == "Node2")
        self.assertEqual(node2["properties"]["mention_count"], "1")
        
        # Check Edge addition
        self.assertEqual(len(existing_edges), 1)

    async def test_reflector_reflect_and_decide_parsing(self):
        reflector = ResearchReflector(self.config, self.mock_llm)
        self.mock_llm.generate_text = AsyncMock(return_value="EVALUATION: CONTINUE\nQUERY: Next specific query")
        
        eval_res, next_q = await reflector.reflect_and_decide("Topic", "Sec1", "Summary", "English")
        self.assertEqual(eval_res, "CONTINUE")
        self.assertEqual(next_q, "Next specific query")

    # --- ResearchReporter Tests ---
    async def test_reporter_finalize_report_citations(self):
        reporter = ResearchReporter(self.mock_llm)
        plan = [
            {"title": "Intro", "summary": "Found X.", "sources": [Source(title="Source 1", link="url1")]}
        ]
        self.mock_llm.generate_text = AsyncMock(return_value="Final synthesized report text with [1].")
        
        report = await reporter.finalize_report("Topic", plan, "English")
        
        self.assertIn("Final synthesized report text with [1].", report)
        self.assertIn("## Sources", report)
        self.assertIn("[1] Source 1 (url1)", report)

if __name__ == '__main__':
    unittest.main()
