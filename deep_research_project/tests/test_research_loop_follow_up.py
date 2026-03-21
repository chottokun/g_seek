import unittest
from unittest.mock import MagicMock, patch
from deep_research_project.core.research_loop import ResearchLoop
from deep_research_project.core.state import ResearchState
from deep_research_project.config.config import Configuration
from deep_research_project.core.prompts import FOLLOW_UP_PROMPT_EN, FOLLOW_UP_PROMPT_JA

class TestResearchLoopFollowUp(unittest.TestCase):
    def setUp(self):
        self.mock_config = MagicMock(spec=Configuration)
        # Mocking LLM_RATE_LIMIT_RPM to avoid issues during LLMClient init if it's called
        self.mock_config.LLM_RATE_LIMIT_RPM = 0

        # We need to patch LLMClient, SearchClient and ContentRetriever
        # because ResearchLoop.__init__ instantiates them.
        self.patch_llm = patch('deep_research_project.core.research_loop.LLMClient')
        self.patch_search = patch('deep_research_project.core.research_loop.SearchClient')
        self.patch_content = patch('deep_research_project.core.research_loop.ContentRetriever')

        self.patch_llm.start()
        self.patch_search.start()
        self.patch_content.start()

    def tearDown(self):
        patch.stopall()

    def test_format_follow_up_prompt_en(self):
        state = ResearchState(research_topic="Test Topic", language="English")
        loop = ResearchLoop(self.mock_config, state)

        report = "This is a final report."
        question = "What is the conclusion?"

        expected = FOLLOW_UP_PROMPT_EN.format(
            final_report=report,
            question=question
        )

        result = loop.format_follow_up_prompt(report, question)
        self.assertEqual(result, expected)
        self.assertIn(report, result)
        self.assertIn(question, result)

    def test_format_follow_up_prompt_ja(self):
        state = ResearchState(research_topic="テストトピック", language="Japanese")
        loop = ResearchLoop(self.mock_config, state)

        report = "これは最終レポートです。"
        question = "結論は何ですか？"

        expected = FOLLOW_UP_PROMPT_JA.format(
            final_report=report,
            question=question
        )

        result = loop.format_follow_up_prompt(report, question)
        self.assertEqual(result, expected)
        self.assertIn(report, result)
        self.assertIn(question, result)

if __name__ == "__main__":
    unittest.main()
