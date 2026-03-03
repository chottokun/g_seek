import unittest
from unittest.mock import MagicMock
from deep_research_project.config.config import Configuration
from deep_research_project.tools.llm_client import LLMClient
from deep_research_project.core.reflection import ResearchReflector
from deep_research_project.core.state import KnowledgeGraphModel, KGNode, KGEdge

class TestReflectionLogic(unittest.TestCase):
    def setUp(self):
        self.config = MagicMock(spec=Configuration)
        self.llm_client = MagicMock(spec=LLMClient)
        self.reflector = ResearchReflector(self.config, self.llm_client)

    def test_merge_into_empty_graph(self):
        """Test 1: Merge into empty graph"""
        existing_nodes = []
        existing_edges = []

        new_kg = KnowledgeGraphModel(
            nodes=[
                KGNode(id="Node1", label="Entity1", type="Concept", properties={"p1": "v1"}, source_urls=["url1"])
            ],
            edges=[
                KGEdge(source="Node1", target="Node2", label="links", properties={"ep1": "ev1"}, source_urls=["url1"])
            ]
        )

        self.reflector._merge_knowledge_graph(new_kg, existing_nodes, existing_edges)

        self.assertEqual(len(existing_nodes), 1)
        self.assertEqual(existing_nodes[0]["id"], "Node1")
        self.assertEqual(existing_nodes[0]["properties"]["mention_count"], "1")

        self.assertEqual(len(existing_edges), 1)
        self.assertEqual(existing_edges[0]["source"], "Node1")
        self.assertEqual(existing_edges[0]["label"], "links")

    def test_update_existing_nodes(self):
        """Test 2: Update existing nodes"""
        existing_nodes = [
            {"id": "Node1", "label": "Entity1", "type": "Concept", "properties": {"mention_count": "1"}, "source_urls": ["url1"]}
        ]
        existing_edges = []

        new_kg = KnowledgeGraphModel(
            nodes=[
                KGNode(id="Node1", label="Entity1", type="Concept", properties={"p2": "v2"}, source_urls=["url2", "url1"])
            ],
            edges=[]
        )

        self.reflector._merge_knowledge_graph(new_kg, existing_nodes, existing_edges)

        self.assertEqual(len(existing_nodes), 1)
        node = existing_nodes[0]
        self.assertEqual(node["properties"]["mention_count"], "2")
        self.assertEqual(node["properties"]["p2"], "v2")
        self.assertCountEqual(node["source_urls"], ["url1", "url2"])

    def test_update_existing_edges(self):
        """Test 3: Update existing edges"""
        existing_nodes = []
        existing_edges = [
            {"source": "N1", "target": "N2", "label": "rel", "properties": {"ep1": "ev1"}, "source_urls": ["url1"]}
        ]

        new_kg = KnowledgeGraphModel(
            nodes=[],
            edges=[
                KGEdge(source="N1", target="N2", label="rel", properties={"ep2": "ev2"}, source_urls=["url2"])
            ]
        )

        self.reflector._merge_knowledge_graph(new_kg, existing_nodes, existing_edges)

        self.assertEqual(len(existing_edges), 1)
        edge = existing_edges[0]
        self.assertEqual(edge["properties"]["ep1"], "ev1")
        self.assertEqual(edge["properties"]["ep2"], "ev2")
        self.assertCountEqual(edge["source_urls"], ["url1", "url2"])

    def test_multiple_occurrences_in_same_batch(self):
        """Test 4: Handle multiple occurrences in same batch"""
        existing_nodes = []
        existing_edges = []

        new_kg = KnowledgeGraphModel(
            nodes=[
                KGNode(id="Node1", label="E1", type="T", properties={}, source_urls=["u1"]),
                KGNode(id="Node1", label="E1", type="T", properties={"p": "v"}, source_urls=["u2"])
            ],
            edges=[
                KGEdge(source="N1", target="N2", label="L", properties={}, source_urls=["u1"]),
                KGEdge(source="N1", target="N2", label="L", properties={"p": "v"}, source_urls=["u2"])
            ]
        )

        self.reflector._merge_knowledge_graph(new_kg, existing_nodes, existing_edges)

        self.assertEqual(len(existing_nodes), 1)
        self.assertEqual(existing_nodes[0]["properties"]["mention_count"], "2")
        self.assertCountEqual(existing_nodes[0]["source_urls"], ["u1", "u2"])

        self.assertEqual(len(existing_edges), 1)
        self.assertCountEqual(existing_edges[0]["source_urls"], ["u1", "u2"])
        self.assertEqual(existing_edges[0]["properties"]["p"], "v")

    def test_edge_cases_and_robustness(self):
        """Test 5: Edge cases and robustness"""
        # Non-integer mention_count
        existing_nodes = [
            {"id": "Node1", "label": "E1", "type": "T", "properties": {"mention_count": "invalid"}, "source_urls": []}
        ]
        existing_edges = []

        new_kg = KnowledgeGraphModel(
            nodes=[KGNode(id="Node1", label="E1", type="T", properties={}, source_urls=[])],
            edges=[]
        )

        self.reflector._merge_knowledge_graph(new_kg, existing_nodes, existing_edges)
        self.assertEqual(existing_nodes[0]["properties"]["mention_count"], "2")

        # Missing properties field
        existing_nodes = [{"id": "Node2", "label": "E2", "type": "T", "source_urls": []}]
        existing_edges = [{"source": "N1", "target": "N2", "label": "L", "source_urls": []}]

        new_kg = KnowledgeGraphModel(
            nodes=[KGNode(id="Node2", label="E2", type="T", properties={"p": "v"}, source_urls=[])],
            edges=[KGEdge(source="N1", target="N2", label="L", properties={"ep": "ev"}, source_urls=[])]
        )

        self.reflector._merge_knowledge_graph(new_kg, existing_nodes, existing_edges)
        self.assertEqual(existing_nodes[0]["properties"]["p"], "v")
        self.assertEqual(existing_edges[0]["properties"]["ep"], "ev")

if __name__ == "__main__":
    unittest.main()
