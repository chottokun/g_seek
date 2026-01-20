import unittest
import asyncio
from unittest.mock import patch, MagicMock, AsyncMock
from deep_research_project.config.config import Configuration
from deep_research_project.core.research_loop import ResearchLoop
from deep_research_project.core.state import ResearchState, ResearchPlanModel, Section

class TestDynamicRefinement(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.mock_config = MagicMock(spec=Configuration)
        self.mock_config.LLM_PROVIDER = "placeholder_llm"
        self.mock_config.INTERACTIVE_MODE = False
        self.mock_config.MAX_RESEARCH_LOOPS = 1
        self.mock_config.MAX_SEARCH_RESULTS_PER_QUERY = 1
        self.mock_config.LLM_MAX_RPM = 60
        self.mock_config.LLM_MAX_PARALLEL_REQUESTS = 5
        self.mock_config.SUMMARIZATION_CHUNK_SIZE_CHARS = 1000
        self.mock_config.SUMMARIZATION_CHUNK_OVERLAP_CHARS = 100

        self.state = ResearchState(research_topic="Test Topic")
        self.state.research_plan = [
            {"title": "Section 1", "description": "Desc 1", "status": "completed", "summary": "Summary 1", "sources": []},
            {"title": "Section 2", "description": "Desc 2", "status": "pending", "summary": "", "sources": []}
        ]
        self.state.current_section_index = 0

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

    async def test_refine_plan_updates_pending_sections(self):
        # Mock LLM to return a refined plan for the remaining part
        refined_plan = ResearchPlanModel(sections=[
            Section(title="Refined Section 2", description="New Desc 2"),
            Section(title="New Section 3", description="Desc 3")
        ])
        self.mock_llm_client.generate_structured = AsyncMock(return_value=refined_plan)

        await self.loop._refine_plan()

        # Plan should now have 1 completed + 2 new pending sections
        self.assertEqual(len(self.state.research_plan), 3)
        self.assertEqual(self.state.research_plan[0]['title'], "Section 1")
        self.assertEqual(self.state.research_plan[0]['status'], "completed")
        self.assertEqual(self.state.research_plan[1]['title'], "Refined Section 2")
        self.assertEqual(self.state.research_plan[1]['status'], "pending")
        self.assertEqual(self.state.research_plan[2]['title'], "New Section 3")
        self.assertEqual(self.state.research_plan[2]['status'], "pending")

    async def test_refine_plan_no_change(self):
        # Mock LLM to return the same plan
        refined_plan = ResearchPlanModel(sections=[
            Section(title="Section 2", description="Desc 2")
        ])
        self.mock_llm_client.generate_structured = AsyncMock(return_value=refined_plan)

        original_plan = self.state.research_plan.copy()
        await self.loop._refine_plan()

        self.assertEqual(len(self.state.research_plan), 2)
        self.assertEqual(self.state.research_plan[1]['title'], "Section 2")

if __name__ == '__main__':
    unittest.main()
