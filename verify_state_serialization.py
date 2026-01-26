
import unittest
import json
from deep_research_project.core.state import ResearchState

class TestResearchStateSerialization(unittest.TestCase):
    def test_serialization(self):
        # Create a state object with some data
        state = ResearchState(research_topic="AI Agents", language="English")
        state.current_query = "What are AI agents?"
        state.search_results = [
            {"title": "Agent 1", "link": "http://example.com/1", "snippet": "Snippet 1"}
        ]
        state.research_plan = [
            {"title": "Intro", "description": "Introduction", "status": "completed", "summary": "Summary 1", "sources": []},
            {"title": "Methods", "description": "Methodology", "status": "pending", "summary": "", "sources": []}
        ]
        state.knowledge_graph_nodes = [{"id": "1", "label": "Agent", "type": "Concept"}]
        state.knowledge_graph_edges = [{"source": "1", "target": "2", "label": "related_to"}]
        state.current_section_index = 1

        # Serialize
        data = state.to_dict()

        # Verify it's JSON serializable
        json_str = json.dumps(data)

        # Deserialize
        new_state = ResearchState.from_dict(json.loads(json_str))

        # Assertions
        self.assertEqual(new_state.research_topic, "AI Agents")
        self.assertEqual(new_state.language, "English")
        self.assertEqual(new_state.current_query, "What are AI agents?")
        self.assertEqual(len(new_state.search_results), 1)
        self.assertEqual(new_state.search_results[0]['title'], "Agent 1")
        self.assertEqual(len(new_state.research_plan), 2)
        self.assertEqual(new_state.research_plan[0]['status'], "completed")
        self.assertEqual(new_state.current_section_index, 1)
        self.assertEqual(len(new_state.knowledge_graph_nodes), 1)

if __name__ == "__main__":
    unittest.main()
