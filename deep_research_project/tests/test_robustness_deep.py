import asyncio
import unittest
from pydantic import ValidationError
from deep_research_project.tools.llm_client import LLMClient
from deep_research_project.core.state import KnowledgeGraphModel, KGNode, KGEdge
from deep_research_project.config.config import Configuration

class TestRobustnessDeep(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.config = Configuration()
        self.config.LLM_PROVIDER = "placeholder_llm"
        self.client = LLMClient(self.config)

    def test_partial_recovery_knowledge_graph(self):
        # Test recovery in KnowledgeGraphModel where nodes/edges are nested lists of BaseModels
        data = {
            "nodes": [
                {"id": "valid_1", "label": "Label 1", "type": "T1"},
                {"id": "invalid_1"}, # Missing mandatory fields (label, type)
                {"id": "valid_2", "label": "Label 2", "type": "T2"}
            ],
            "edges": [
                {"source": "v1", "target": "v2", "label": "related"},
                {"source": "v1"} # Missing target and label
            ]
        }
        
        # Test direct call to internal recovery logic
        result = self.client._partial_model_recovery(data, KnowledgeGraphModel)
        
        self.assertIsInstance(result, KnowledgeGraphModel)
        # Should have recovered 2 valid nodes out of 3
        self.assertEqual(len(result.nodes), 2)
        self.assertEqual(result.nodes[0].id, "valid_1")
        self.assertEqual(result.nodes[1].id, "valid_2")
        
        # Should have recovered 1 valid edge out of 2
        self.assertEqual(len(result.edges), 1)
        self.assertEqual(result.edges[0].source, "v1")
        self.assertEqual(result.edges[0].target, "v2")
        print("Test Deep Partial Recovery (KnowledgeGraph): Success")

    def test_robust_extract_total_garbage(self):
        # Complete garbage that doesn't look like JSON at all
        garbage_text = "Wait, I don't know the answer. I will just talk about weather. It is sunny."
        
        # Should fallback to empty model instead of raising
        result = self.client._robust_json_extract(garbage_text, KnowledgeGraphModel)
        self.assertIsInstance(result, KnowledgeGraphModel)
        self.assertEqual(len(result.nodes), 0)
        self.assertEqual(len(result.edges), 0)
        print("Test Robust Extract (Total Garbage): Success")

    def test_state_source_consistency(self):
        # Verify that Source objects (Pydantic) work well inside TypedDict structures in state
        from deep_research_project.core.state import ResearchState, Source
        state = ResearchState("Topic")
        source = Source(title="T", link="L")
        
        # ResearchState uses a list for research_plan containing dictionaries
        state.research_plan.append({
            "title": "Sec 1",
            "description": "Desc",
            "status": "pending",
            "summary": "",
            "sources": [source]
        })
        
        self.assertEqual(state.research_plan[0]["sources"][0].title, "T")
        # Check that we can access it as an object
        self.assertEqual(getattr(state.research_plan[0]["sources"][0], 'link'), "L")
        print("Test State/Source Consistency: Success")

if __name__ == "__main__":
    unittest.main()
