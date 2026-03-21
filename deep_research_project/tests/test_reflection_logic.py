import unittest
from unittest.mock import MagicMock
from deep_research_project.config.config import Configuration
from deep_research_project.tools.llm_client import LLMClient
from deep_research_project.core.reflection import ResearchReflector
from deep_research_project.core.state import KnowledgeGraphModel, KGNode, KGEdge

class TestReflectionLogic(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.config = MagicMock(spec=Configuration)
        self.llm_client = MagicMock(spec=LLMClient)
        self.reflector = ResearchReflector(self.config, self.llm_client)

    async def test_reflect_and_decide_early_return(self):
        """Test: early return when accumulated_summary is empty"""
        topic = "AI agents"
        evaluation, next_query = await self.reflector.reflect_and_decide(
            topic=topic,
            section_title="Intro",
            section_description="Introduction to AI",
            accumulated_summary="",
            language="English"
        )
        self.assertEqual(evaluation, "CONTINUE")
        self.assertEqual(next_query, topic)

        # Test with whitespace
        evaluation, next_query = await self.reflector.reflect_and_decide(
            topic=topic,
            section_title="Intro",
            section_description="Introduction to AI",
            accumulated_summary="   \n  ",
            language="English"
        )
        self.assertEqual(evaluation, "CONTINUE")
        self.assertEqual(next_query, topic)

    async def test_reflect_and_decide_parsing(self):
        """Test parsing of LLM response for EVALUATION and QUERY"""
        topic = "AI agents"

        # Test CONTINUE with query
        self.llm_client.generate_text.return_value = "EVALUATION: CONTINUE\nQUERY: latest AI agent frameworks"
        evaluation, next_query = await self.reflector.reflect_and_decide(
            topic=topic,
            section_title="Intro",
            section_description="Intro",
            accumulated_summary="Some info",
            language="English"
        )
        self.assertEqual(evaluation, "CONTINUE")
        self.assertEqual(next_query, "latest AI agent frameworks")

        # Test CONCLUDE
        self.llm_client.generate_text.return_value = "EVALUATION: CONCLUDE\nQUERY: None"
        evaluation, next_query = await self.reflector.reflect_and_decide(
            topic=topic,
            section_title="Intro",
            section_description="Intro",
            accumulated_summary="Some info",
            language="English"
        )
        self.assertEqual(evaluation, "CONCLUDE")
        self.assertIsNone(next_query)

        # Test variations in formatting
        self.llm_client.generate_text.return_value = "evaluation: continue\nquery: \"multi-agent systems\""
        evaluation, next_query = await self.reflector.reflect_and_decide(
            topic=topic,
            section_title="Intro",
            section_description="Intro",
            accumulated_summary="Some info",
            language="English"
        )
        self.assertEqual(evaluation, "CONTINUE")
        self.assertEqual(next_query, "multi-agent systems")

    async def test_reflect_and_decide_languages(self):
        """Test that correct prompts are used for different languages"""
        topic = "AI agents"
        self.llm_client.generate_text.return_value = "EVALUATION: CONCLUDE\nQUERY: None"

        # English
        await self.reflector.reflect_and_decide(
            topic=topic,
            section_title="Intro",
            section_description="Intro",
            accumulated_summary="Some info",
            language="English"
        )
        call_args = self.llm_client.generate_text.call_args
        self.assertIn("Research Topic: AI agents", call_args.kwargs['prompt'])
        self.assertIn("Section Objective: Intro", call_args.kwargs['prompt'])

        # Japanese
        await self.reflector.reflect_and_decide(
            topic=topic,
            section_title="導入",
            section_description="導入説明",
            accumulated_summary="情報",
            language="Japanese"
        )
        call_args = self.llm_client.generate_text.call_args
        self.assertIn("リサーチトピック: AI agents", call_args.kwargs['prompt'])
        self.assertIn("セクション: 導入", call_args.kwargs['prompt'])

    async def test_reflect_and_decide_sanitization(self):
        """Test that next_query is sanitized"""
        topic = "AI agents"
        # Long query and markdown
        long_query = "A" * 200
        self.llm_client.generate_text.return_value = f"EVALUATION: CONTINUE\nQUERY: **{long_query}**"

        evaluation, next_query = await self.reflector.reflect_and_decide(
            topic=topic,
            section_title="Intro",
            section_description="Intro",
            accumulated_summary="Some info",
            language="English"
        )
        self.assertEqual(evaluation, "CONTINUE")
        self.assertTrue(len(next_query) <= 100)
        self.assertNotIn("**", next_query)

    async def test_reflect_alias(self):
        """Test the reflect alias method"""
        topic = "AI agents"
        self.llm_client.generate_text.return_value = "EVALUATION: CONTINUE\nQUERY: next step"

        result = await self.reflector.reflect(
            topic=topic,
            section_title="Intro",
            section_description="Intro",
            accumulated_summary="Some info",
            language="English"
        )
        self.assertEqual(result["evaluation"], "CONTINUE")
        self.assertEqual(result["query"], "next step")

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
