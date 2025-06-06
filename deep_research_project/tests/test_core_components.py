import unittest
import os
from unittest.mock import patch, MagicMock

# Modules to be tested
from deep_research_project.config.config import Configuration
from deep_research_project.core.research_loop import ResearchLoop
from deep_research_project.core.state import ResearchState, Source
from deep_research_project.tools.llm_client import LLMClient

# Configure logging for tests (optional, but can be helpful)
import logging
logging.basicConfig(level=logging.INFO) # Keep it INFO to avoid too much noise, or DEBUG for detailed test output

class TestConfiguration(unittest.TestCase):
    @patch.dict(os.environ, {"LLM_MAX_TOKENS": "512"})
    def test_llm_max_tokens_from_env(self):
        config = Configuration()
        self.assertEqual(config.LLM_MAX_TOKENS, 512)

    @patch.dict(os.environ, {}, clear=True)
    def test_llm_max_tokens_default(self):
        # Ensure LLM_MAX_TOKENS is not in environ for this test
        if "LLM_MAX_TOKENS" in os.environ:
            del os.environ["LLM_MAX_TOKENS"]
        config = Configuration()
        self.assertEqual(config.LLM_MAX_TOKENS, 1024) # Default value

class TestLLMClientConfiguration(unittest.TestCase):
    @patch.dict(os.environ, {"LLM_PROVIDER": "openai", "OPENAI_API_KEY": "test_key", "LLM_MAX_TOKENS": "256"})
    @patch('langchain_openai.ChatOpenAI') # Mock the actual OpenAI client
    def test_generate_text_uses_config_max_tokens_openai(self, MockChatOpenAI):
        mock_llm_instance = MockChatOpenAI.return_value
        mock_llm_instance.invoke.return_value = MagicMock(content="Test response")

        config = Configuration() # LLM_MAX_TOKENS will be 256 from env
        llm_client = LLMClient(config)

        llm_client.generate_text("test prompt")

        mock_llm_instance.invoke.assert_called_once()
        call_args = mock_llm_instance.invoke.call_args
        self.assertIn('max_tokens', call_args.kwargs)
        self.assertEqual(call_args.kwargs['max_tokens'], 256)

    @patch.dict(os.environ, {"LLM_PROVIDER": "placeholder_llm", "LLM_MAX_TOKENS": "128"})
    def test_generate_text_uses_config_max_tokens_placeholder(self):
        # This test is more conceptual for the placeholder as it doesn't directly use 'max_tokens' in its simulation.
        # However, we can verify the config value is accessible if needed.
        # For now, the primary check is on providers that explicitly use max_tokens like OpenAI.
        # If placeholder were to use it, we'd mock its internal logic.
        config = Configuration()
        llm_client = LLMClient(config) # LLM_MAX_TOKENS will be 128 from config
        # If the placeholder's generate_text were to use self.config.LLM_MAX_TOKENS for some logic,
        # we would test that logic here. For now, this test confirms LLMClient initializes with it.
        self.assertEqual(llm_client.config.LLM_MAX_TOKENS, 128)
        # Example: If placeholder had a conditional path based on max_tokens
        # with patch.object(llm_client, 'llm', "PlaceholderLLMInstance") as mock_placeholder:
        #    llm_client.generate_text("test prompt")
        #    # Add assertions based on how placeholder would use LLM_MAX_TOKENS


class TestResearchLoopFinalizeSummary(unittest.TestCase):
    def setUp(self):
        self.mock_config = MagicMock(spec=Configuration)
        self.mock_config.LLM_PROVIDER = "placeholder_llm" # Use placeholder for LLMClient
        self.mock_config.LOG_LEVEL = "DEBUG"
        # other config attributes as needed by ResearchLoop or LLMClient initialization
        self.mock_config.OPENAI_API_KEY = None
        self.mock_config.OLLAMA_BASE_URL = None
        self.mock_config.MAX_SEARCH_RESULTS_PER_QUERY = 3
        self.mock_config.LLM_MAX_TOKENS = 1024 # Default or any value

        # Mock LLMClient instance that will be created within ResearchLoop
        self.mock_llm_client_instance = MagicMock(spec=LLMClient)

        # Patch the LLMClient constructor to return our mock_llm_client_instance
        self.llm_client_patcher = patch('deep_research_project.core.research_loop.LLMClient', return_value=self.mock_llm_client_instance)
        self.MockLLMClient = self.llm_client_patcher.start()
        self.addCleanup(self.llm_client_patcher.stop)

        # Patch SearchClient as it's also initialized in ResearchLoop
        self.search_client_patcher = patch('deep_research_project.core.research_loop.SearchClient')
        self.MockSearchClient = self.search_client_patcher.start()
        self.addCleanup(self.search_client_patcher.stop)


    def test_finalize_summary_empty_accumulation(self):
        state = ResearchState(research_topic="Test Topic")
        state.accumulated_summary = "" # Empty
        state.sources_gathered = []

        loop = ResearchLoop(config=self.mock_config, state=state)
        loop._finalize_summary()

        self.mock_llm_client_instance.generate_text.assert_not_called()
        self.assertIn("No information was gathered", loop.state.final_report)
        self.assertNotIn("## Sources", loop.state.final_report)

    def test_finalize_summary_with_content_and_sources(self):
        state = ResearchState(research_topic="Test Topic")
        state.accumulated_summary = "Some interesting findings."
        state.sources_gathered = [Source(title="Source 1", link="http://example.com/s1")]

        self.mock_llm_client_instance.generate_text.return_value = "This is the LLM generated report."

        loop = ResearchLoop(config=self.mock_config, state=state)
        loop._finalize_summary()

        self.mock_llm_client_instance.generate_text.assert_called_once()
        call_args = self.mock_llm_client_instance.generate_text.call_args
        prompt = call_args.kwargs['prompt']
        self.assertIn("Research Topic: Test Topic", prompt)
        self.assertIn("Accumulated Information:\nSome interesting findings.", prompt)

        self.assertIn("This is the LLM generated report.", loop.state.final_report)
        self.assertIn("## Sources", loop.state.final_report)
        self.assertIn("1. Source 1 (http://example.com/s1)", loop.state.final_report)

    def test_finalize_summary_llm_error(self):
        state = ResearchState(research_topic="Test Topic Error Case")
        state.accumulated_summary = "Valuable data here."
        state.sources_gathered = []

        self.mock_llm_client_instance.generate_text.side_effect = Exception("LLM API Failure")

        loop = ResearchLoop(config=self.mock_config, state=state)
        loop._finalize_summary()

        self.mock_llm_client_instance.generate_text.assert_called_once() # Attempt was made
        self.assertIn("# Research Report: Test Topic Error Case", loop.state.final_report)
        self.assertIn("## Accumulated Findings", loop.state.final_report)
        self.assertIn("Valuable data here.", loop.state.final_report)
        self.assertIn("An error occurred while generating the final synthesized report", loop.state.final_report)


class TestResearchLoopReflectOnSummary(unittest.TestCase):
    def setUp(self):
        self.mock_config = MagicMock(spec=Configuration)
        self.mock_config.LLM_PROVIDER = "placeholder_llm"
        self.mock_config.LOG_LEVEL = "DEBUG"
        self.mock_config.MAX_RESEARCH_LOOPS = 3
        self.mock_config.OPENAI_API_KEY = None
        self.mock_config.OLLAMA_BASE_URL = None
        self.mock_config.MAX_SEARCH_RESULTS_PER_QUERY = 3
        self.mock_config.LLM_MAX_TOKENS = 1024

        self.mock_llm_client_instance = MagicMock(spec=LLMClient)

        self.llm_client_patcher = patch('deep_research_project.core.research_loop.LLMClient', return_value=self.mock_llm_client_instance)
        self.MockLLMClient = self.llm_client_patcher.start()
        self.addCleanup(self.llm_client_patcher.stop)

        self.search_client_patcher = patch('deep_research_project.core.research_loop.SearchClient')
        self.MockSearchClient = self.search_client_patcher.start()
        self.addCleanup(self.search_client_patcher.stop)

        self.state = ResearchState(research_topic="Initial Topic")
        self.state.accumulated_summary = "Initial summary."
        self.state.completed_loops = 0

        self.loop = ResearchLoop(config=self.mock_config, state=self.state)

    def test_reflect_on_summary_continue(self):
        self.mock_llm_client_instance.generate_text.return_value = "EVALUATION: CONTINUE\nQUERY: new_query_for_science"
        self.loop._reflect_on_summary()
        self.assertEqual(self.state.current_query, "new_query_for_science")

    def test_reflect_on_summary_modify_topic(self):
        self.mock_llm_client_instance.generate_text.return_value = "EVALUATION: MODIFY_TOPIC\nQUERY: better_topic_query"
        self.loop._reflect_on_summary()
        self.assertEqual(self.state.current_query, "Refined Topic Query: better_topic_query")

    def test_reflect_on_summary_conclude(self):
        self.mock_llm_client_instance.generate_text.return_value = "EVALUATION: CONCLUDE\nQUERY: None"
        self.loop._reflect_on_summary()
        self.assertIsNone(self.state.current_query)

    def test_reflect_on_summary_continue_but_query_is_none(self):
        self.mock_llm_client_instance.generate_text.return_value = "EVALUATION: CONTINUE\nQUERY: None"
        self.loop._reflect_on_summary()
        self.assertIsNone(self.state.current_query)

    def test_reflect_on_summary_modify_topic_but_query_is_none(self):
        self.mock_llm_client_instance.generate_text.return_value = "EVALUATION: MODIFY_TOPIC\nQUERY: None"
        self.loop._reflect_on_summary()
        self.assertIsNone(self.state.current_query)

    def test_reflect_on_summary_invalid_llm_response_format(self):
        self.mock_llm_client_instance.generate_text.return_value = "This is not the droid you are looking for."
        self.loop._reflect_on_summary()
        self.assertIsNone(self.state.current_query) # Should default to terminating

    def test_reflect_on_summary_parsing_error_incomplete_evaluation(self):
        self.mock_llm_client_instance.generate_text.return_value = "EVALUATION:\nQUERY: some_query"
        self.loop._reflect_on_summary()
        self.assertIsNone(self.state.current_query) # Should default to terminating on parsing error (ERROR state)

    def test_reflect_on_summary_llm_call_raises_exception(self):
        self.mock_llm_client_instance.generate_text.side_effect = Exception("LLM is down")
        self.loop._reflect_on_summary()
        self.assertIsNone(self.state.current_query)

if __name__ == '__main__':
    unittest.main(argv=['first-arg-is-ignored'], exit=False)
