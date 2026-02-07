import unittest
from unittest.mock import MagicMock, AsyncMock, patch
from deep_research_project.core.research_loop import ResearchLoop
from deep_research_project.core.state import ResearchState, KnowledgeGraphModel, KGNode, KGEdge
from deep_research_project.config.config import Configuration

class TestKGOptimization(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.config = Configuration()
        self.state = ResearchState(research_topic="Test Topic")

        # Pre-populate state
        self.state.knowledge_graph_nodes = [
            {"id": "node_1", "label": "Node 1", "type": "Type A"},
            {"id": "node_2", "label": "Node 2", "type": "Type B"}
        ]
        self.state.knowledge_graph_edges = [
            {"source": "node_1", "target": "node_2", "label": "relates_to"}
        ]

        # Mock dependencies
        with patch('deep_research_project.core.research_loop.LLMClient') as MockLLMClient, \
             patch('deep_research_project.core.research_loop.SearchClient') as MockSearchClient, \
             patch('deep_research_project.core.research_loop.ContentRetriever') as MockContentRetriever:

            self.loop = ResearchLoop(self.config, self.state)
            # Replace the real llm_client with a mock
            self.loop.llm_client = AsyncMock()

    def test_init_populates_sets(self):
        """Test that __init__ correctly populates the cached sets."""
        self.assertEqual(len(self.loop._kg_node_ids), 2)
        self.assertIn("node_1", self.loop._kg_node_ids)
        self.assertIn("node_2", self.loop._kg_node_ids)

        self.assertEqual(len(self.loop._kg_edge_keys), 1)
        self.assertIn(("node_1", "node_2", "relates_to"), self.loop._kg_edge_keys)

    async def test_extract_entities_adds_new_items(self):
        """Test that new nodes/edges are added to state and sets."""
        # Setup mock return value
        new_kg = KnowledgeGraphModel(
            nodes=[
                KGNode(id="node_1", label="Node 1", type="Type A"), # Duplicate
                KGNode(id="node_3", label="Node 3", type="Type C")  # New
            ],
            edges=[
                KGEdge(source="node_1", target="node_2", label="relates_to"), # Duplicate
                KGEdge(source="node_2", target="node_3", label="connected_to") # New
            ]
        )
        self.loop.llm_client.generate_structured.return_value = new_kg
        self.loop.state.new_information = "Some text to trigger extraction."

        await self.loop._extract_entities_and_relations()

        # Verify state
        self.assertEqual(len(self.loop.state.knowledge_graph_nodes), 3)
        self.assertEqual(self.loop.state.knowledge_graph_nodes[-1]['id'], "node_3")

        self.assertEqual(len(self.loop.state.knowledge_graph_edges), 2)
        self.assertEqual(self.loop.state.knowledge_graph_edges[-1]['target'], "node_3")

        # Verify cached sets
        self.assertEqual(len(self.loop._kg_node_ids), 3)
        self.assertIn("node_3", self.loop._kg_node_ids)

        self.assertEqual(len(self.loop._kg_edge_keys), 2)
        self.assertIn(("node_2", "node_3", "connected_to"), self.loop._kg_edge_keys)
