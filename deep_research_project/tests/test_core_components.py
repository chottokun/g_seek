import unittest
import os
import asyncio
from unittest.mock import patch, MagicMock, AsyncMock

# Modules to be tested
from deep_research_project.config.config import Configuration
from deep_research_project.core.research_loop import ResearchLoop, split_text_into_chunks
from deep_research_project.core.state import ResearchState, Source, SearchResult, ResearchPlanModel, Section, KnowledgeGraphModel
from deep_research_project.tools.llm_client import LLMClient

class TestAsyncResearchLoop(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.mock_config = MagicMock(spec=Configuration)
        self.mock_config.LLM_PROVIDER = "placeholder_llm"
        self.mock_config.SEARCH_API = "duckduckgo"
        self.mock_config.INTERACTIVE_MODE = False
        self.mock_config.MAX_RESEARCH_LOOPS = 2
        self.mock_config.MAX_SEARCH_RESULTS_PER_QUERY = 3
        self.mock_config.USE_SNIPPETS_ONLY_MODE = False
        self.mock_config.SUMMARIZATION_CHUNK_SIZE_CHARS = 1000
        self.mock_config.SUMMARIZATION_CHUNK_OVERLAP_CHARS = 100
        self.mock_config.LOG_LEVEL = "INFO"

        self.state = ResearchState(research_topic="AI in Healthcare")

        # Patch clients
        self.llm_patcher = patch('deep_research_project.core.research_loop.LLMClient')
        self.search_patcher = patch('deep_research_project.core.research_loop.SearchClient')
        self.content_patcher = patch('deep_research_project.core.research_loop.ContentRetriever')

        self.mock_llm_client = self.llm_patcher.start().return_value
        self.mock_search_client = self.search_patcher.start().return_value
        self.mock_content_retriever = self.content_patcher.start().return_value

        self.loop = ResearchLoop(self.mock_config, self.state)

    async def asyncTearDown(self):
        self.llm_patcher.stop()
        self.search_patcher.stop()
        self.content_patcher.stop()

    async def test_generate_research_plan_structured(self):
        # Mock structured output
        mock_plan = ResearchPlanModel(sections=[
            Section(title="Intro", description="Overview"),
            Section(title="Body", description="Details")
        ])
        self.mock_llm_client.generate_structured = AsyncMock(return_value=mock_plan)

        await self.loop._generate_research_plan()

        self.assertEqual(len(self.state.research_plan), 2)
        self.assertEqual(self.state.research_plan[0]['title'], "Intro")
        self.mock_llm_client.generate_structured.assert_called_once()

    async def test_web_search_updates_state(self):
        self.state.current_query = "AI medical imaging"
        mock_results = [SearchResult(title="Study 1", link="http://s1.com", snippet="Interesting")]
        self.mock_search_client.search = AsyncMock(return_value=mock_results)

        await self.loop._web_search()

        self.assertEqual(self.state.search_results, mock_results)
        self.assertTrue(self.state.pending_source_selection)

    async def test_summarize_sources_accumulates_data(self):
        self.state.current_query = "Query A"
        selected = [SearchResult(title="S1", link="http://s1.com", snippet="Snippet 1")]
        self.mock_content_retriever.retrieve_and_extract = AsyncMock(return_value="Full content 1")
        self.mock_llm_client.generate_text = AsyncMock(side_effect=["Summary 1", "Final Summary"])

        # Mock KG extraction to avoid errors
        self.mock_llm_client.generate_structured = AsyncMock(return_value=KnowledgeGraphModel(nodes=[], edges=[]))

        await self.loop._summarize_sources(selected)

        self.assertEqual(self.state.new_information, "Final Summary")
        self.assertIn("## Query A", self.state.accumulated_summary)
        self.assertEqual(len(self.state.sources_gathered), 1)

    async def test_finalize_summary_with_citations(self):
        self.state.research_plan = [
            {"title": "Sec 1", "summary": "Info 1", "sources": [Source(title="Source 1", link="s1")], "status": "completed"}
        ]
        self.mock_llm_client.generate_text = AsyncMock(return_value="Report with [1]")

        await self.loop._finalize_summary()

        self.assertIn("Report with [1]", self.state.final_report)
        self.assertIn("## Sources", self.state.final_report)
        self.assertIn("[1] Source 1 (s1)", self.state.final_report)

        # Check if citations were requested in prompt
        call_args = self.mock_llm_client.generate_text.call_args
        prompt = call_args.kwargs['prompt']
        # Since default language is Japanese now
        self.assertTrue("numbered in-text citations" in prompt.lower() or "番号付きのインライン引用" in prompt)
        self.assertIn("[1]", prompt)

class TestSplitTextIntoChunks(unittest.TestCase):
    def test_basic_chunking(self):
        text = "1234567890"
        chunks = split_text_into_chunks(text, 5, 2)
        self.assertEqual(chunks, ["12345", "45678", "7890"])

if __name__ == '__main__':
    unittest.main()
