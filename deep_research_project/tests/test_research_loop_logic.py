import unittest
from unittest.mock import MagicMock, AsyncMock, patch
from deep_research_project.config.config import Configuration
from deep_research_project.core.research_loop import ResearchLoop
from deep_research_project.core.state import ResearchState, KnowledgeGraphModel, KGNode, KGEdge

class TestResearchLoopLogic(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.mock_config = MagicMock(spec=Configuration)
        self.mock_config.INTERACTIVE_MODE = False
        self.mock_config.MAX_RESEARCH_LOOPS = 2
        self.mock_config.LANGUAGE = "English"
        
        self.state = ResearchState(research_topic="AI Testing")
        
        with patch('deep_research_project.core.research_loop.LLMClient'), \
             patch('deep_research_project.core.research_loop.SearchClient'), \
             patch('deep_research_project.core.research_loop.ContentRetriever'):
            self.loop = ResearchLoop(self.mock_config, self.state)

    async def test_extract_entities_and_relations_merging(self):
        # Initial state
        self.state.knowledge_graph_nodes = [{"id": "n1", "label": "Node 1", "type": "T1"}]
        self.state.knowledge_graph_edges = [{"source": "n1", "target": "n2", "label": "e1"}]
        self.state.new_information = "Some new data to extract from."
        
        # Mocking LLM structured output
        mock_kg = KnowledgeGraphModel(
            nodes=[
                KGNode(id="n1", label="Node 1", type="T1"), # Duplicate
                KGNode(id="n2", label="Node 2", type="T2")  # New
            ],
            edges=[
                KGEdge(source="n1", target="n2", label="e1"), # Duplicate
                KGEdge(source="n2", target="n3", label="e2")  # New
            ]
        )
        self.loop.llm_client.generate_structured = AsyncMock(return_value=mock_kg)
        
        await self.loop._extract_entities_and_relations()
        
        self.assertEqual(len(self.state.knowledge_graph_nodes), 2)
        self.assertEqual(len(self.state.knowledge_graph_edges), 2)
        self.assertIn("n2", [n['id'] for n in self.state.knowledge_graph_nodes])

    async def test_reflect_on_summary_parsing(self):
        self.loop.llm_client.generate_text = AsyncMock(side_effect=[
            "EVALUATION: CONTINUE\nQUERY: Deep AI testing",
            "EVALUATION: CONCLUDE\nQUERY: None"
        ])
        
        await self.loop._reflect_on_summary()
        self.assertEqual(self.state.proposed_query, "Deep AI testing")
        
        await self.loop._reflect_on_summary()
        self.assertIsNone(self.state.proposed_query)

    async def test_finalize_summary_no_sources(self):
        self.state.research_plan = [
            {"title": "Section 1", "summary": "Found something.", "sources": [], "status": "completed"}
        ]
        self.loop.llm_client.generate_text = AsyncMock(return_value="Final report.")
        
        await self.loop._finalize_summary()
        
        self.assertIn("Final report.", self.state.final_report)
        self.assertNotIn("## Sources", self.state.final_report)
        
        # Verify prompt instructions
        prompt = self.loop.llm_client.generate_text.call_args.kwargs['prompt']
        self.assertIn("do not use in-text citations", prompt.lower())

    def test_get_current_section(self):
        self.state.research_plan = [{"title": "S1"}, {"title": "S2"}]
        self.state.current_section_index = 0
        self.assertEqual(self.loop._get_current_section()['title'], "S1")
        
        self.state.current_section_index = 5
        self.assertIsNone(self.loop._get_current_section())

if __name__ == '__main__':
    unittest.main()
