import unittest
import os
from unittest.mock import patch, MagicMock

# Modules to be tested
from deep_research_project.config.config import Configuration
from deep_research_project.core.research_loop import ResearchLoop, split_text_into_chunks
from deep_research_project.core.state import ResearchState, Source, SearchResult
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


class TestSplitTextIntoChunks(unittest.TestCase):
    def test_empty_text(self):
        self.assertEqual(split_text_into_chunks("", 100, 10), [])

    def test_none_text(self):
        self.assertEqual(split_text_into_chunks(None, 100, 10), [])

    def test_text_shorter_than_chunk_size(self):
        self.assertEqual(split_text_into_chunks("abc", 10, 2), ["abc"])

    def test_simple_chunking_no_overlap(self):
        text = "abcdefghij" # len 10
        self.assertEqual(split_text_into_chunks(text, 5, 0), ["abcde", "fghij"])

    def test_chunking_with_overlap(self):
        text = "abcdefghij" # len 10
        # chunk1: "abcde" (idx=0, end_idx=5) -> next_idx = 0 + (5-2) = 3
        # chunk2: "defgh" (idx=3, end_idx=8) -> next_idx = 3 + (5-2) = 6
        # chunk3: "ghij"  (idx=6, end_idx=11) -> end_idx >= len, break
        self.assertEqual(split_text_into_chunks(text, 5, 2), ["abcde", "defgh", "ghij"])

    def test_chunking_exact_multiple_no_overlap(self):
        text = "abcdefghij"
        self.assertEqual(split_text_into_chunks(text, 5, 0), ["abcde", "fghij"])

    def test_chunking_exact_multiple_with_overlap(self):
        text = "abcdefghijklmno" # len 15
        chunk_size = 5
        overlap = 1
        # c1: "abcde" (idx=0, end=5) -> next_idx = 0 + (5-1) = 4
        # c2: "efghi" (idx=4, end=9) -> next_idx = 4 + (5-1) = 8
        # c3: "ijklm" (idx=8, end=13) -> next_idx = 8 + (5-1) = 12
        # c4: "mno"   (idx=12, end=17) -> end_idx >= len, break
        expected = ["abcde", "efghi", "ijklm", "mno"]
        self.assertEqual(split_text_into_chunks(text, chunk_size, overlap), expected)

    def test_invalid_chunk_size_raises_value_error(self):
        with self.assertRaises(ValueError):
            split_text_into_chunks("some text", 0, 0)
        with self.assertRaises(ValueError):
            split_text_into_chunks("some text", -1, 0)

    def test_invalid_overlap_raises_value_error(self):
        with self.assertRaises(ValueError): # overlap < 0
            split_text_into_chunks("some text", 10, -1)
        with self.assertRaises(ValueError): # overlap == chunk_size
            split_text_into_chunks("some text", 10, 10)
        with self.assertRaises(ValueError): # overlap > chunk_size
            split_text_into_chunks("some text", 10, 11)

    def test_non_positive_step_safety_break_is_not_hit_with_valid_inputs(self):
        # This test implicitly checks that valid inputs don't cause the safety break.
        # The ValueError checks for overlap >= chunk_size already cover the direct cause.
        text = "abcdefghij"
        # This should not hang or error out due to the internal safety break
        split_text_into_chunks(text, 5, 2)
        # For an actual non-positive step, ValueError is raised before loop.
        # So, direct testing of the safety break log is hard without deeper mocking.

    def test_last_chunk_smaller(self):
        text = "abcdefg" # len 7
        # c1: "abcde" (idx=0, end=5) -> next_idx = 0 + (5-0) = 5
        # c2: "fg"    (idx=5, end=10) -> end_idx >= len, break
        self.assertEqual(split_text_into_chunks(text, 5, 0), ["abcde", "fg"])


class TestResearchLoopKnowledgeGraph(unittest.TestCase):
    def setUp(self):
        self.mock_config = MagicMock(spec=Configuration)
        # Set necessary config attributes for ResearchLoop and its components
        self.mock_config.LLM_PROVIDER = "placeholder_llm"
        self.mock_config.LOG_LEVEL = "DEBUG"
        self.mock_config.OPENAI_API_KEY = None # Ensure not needed if placeholder
        self.mock_config.OLLAMA_BASE_URL = None # Ensure not needed if placeholder
        self.mock_config.MAX_SEARCH_RESULTS_PER_QUERY = 3
        self.mock_config.LLM_MAX_TOKENS = 1024
        self.mock_config.INTERACTIVE_MODE = False # Default for tests unless specified

        self.state = ResearchState(research_topic="KG Test Topic")

        # Mock LLMClient that ResearchLoop will instantiate
        self.mock_llm_client_instance = MagicMock(spec=LLMClient)

        # Patch the LLMClient constructor within the research_loop module
        self.llm_client_patcher = patch('deep_research_project.core.research_loop.LLMClient', return_value=self.mock_llm_client_instance)
        self.MockLLMClient = self.llm_client_patcher.start()
        self.addCleanup(self.llm_client_patcher.stop)

        # Patch SearchClient as it's also initialized in ResearchLoop (though not directly used by _extract_entities_and_relations)
        self.search_client_patcher = patch('deep_research_project.core.research_loop.SearchClient')
        self.MockSearchClient = self.search_client_patcher.start()
        self.addCleanup(self.search_client_patcher.stop)

        # Patch ContentRetriever
        self.content_retriever_patcher = patch('deep_research_project.core.research_loop.ContentRetriever')
        self.MockContentRetriever = self.content_retriever_patcher.start()
        self.addCleanup(self.content_retriever_patcher.stop)

        self.research_loop = ResearchLoop(config=self.mock_config, state=self.state)

    def test_successful_extraction(self):
        self.state.new_information = "Alice is a person. Bob is a person. Alice knows Bob."
        expected_nodes = [{"id": "alice", "label": "Alice", "type": "Person"}]
        expected_edges = [{"source": "alice", "target": "bob", "label": "knows"}]
        self.mock_llm_client_instance.generate_text.return_value = \
            f'{{"nodes": {expected_nodes!r}, "edges": {expected_edges!r}}}'.replace("'", '"') # Ensure valid JSON

        self.research_loop._extract_entities_and_relations()

        self.mock_llm_client_instance.generate_text.assert_called_once()
        self.assertEqual(self.state.knowledge_graph_nodes, expected_nodes)
        self.assertEqual(self.state.knowledge_graph_edges, expected_edges)

    def test_llm_returns_invalid_json(self):
        self.state.new_information = "Some text to process."
        # Invalid JSON (single quotes)
        self.mock_llm_client_instance.generate_text.return_value = "{'nodes': [{'id': 'node1', 'label': 'Entity A'}]}"

        self.research_loop._extract_entities_and_relations()

        self.mock_llm_client_instance.generate_text.assert_called_once()
        self.assertEqual(self.state.knowledge_graph_nodes, [])
        self.assertEqual(self.state.knowledge_graph_edges, [])
        # TODO: Add log capture assertion if possible and desired

    def test_llm_returns_json_with_missing_keys(self):
        self.state.new_information = "Some text."
        self.mock_llm_client_instance.generate_text.return_value = '{"data": [], "info": "missing keys"}'

        self.research_loop._extract_entities_and_relations()

        self.mock_llm_client_instance.generate_text.assert_called_once()
        self.assertEqual(self.state.knowledge_graph_nodes, [])
        self.assertEqual(self.state.knowledge_graph_edges, [])

    def test_no_new_information(self):
        self.state.new_information = None

        self.research_loop._extract_entities_and_relations()

        self.mock_llm_client_instance.generate_text.assert_not_called()
        self.assertEqual(self.state.knowledge_graph_nodes, [])
        self.assertEqual(self.state.knowledge_graph_edges, [])

    def test_new_information_is_empty_string(self):
        self.state.new_information = "  " # Whitespace only

        self.research_loop._extract_entities_and_relations()

        self.mock_llm_client_instance.generate_text.assert_not_called()
        self.assertEqual(self.state.knowledge_graph_nodes, [])
        self.assertEqual(self.state.knowledge_graph_edges, [])

    def test_new_information_indicates_error(self):
        self.state.new_information = "Error occurred during summary generation."

        self.research_loop._extract_entities_and_relations()

        self.mock_llm_client_instance.generate_text.assert_not_called()
        self.assertEqual(self.state.knowledge_graph_nodes, [])
        self.assertEqual(self.state.knowledge_graph_edges, [])

    def test_new_information_indicates_no_sources_selected(self):
        self.state.new_information = "No sources were selected for summarization."

        self.research_loop._extract_entities_and_relations()

        self.mock_llm_client_instance.generate_text.assert_not_called()
        self.assertEqual(self.state.knowledge_graph_nodes, [])
        self.assertEqual(self.state.knowledge_graph_edges, [])

    def test_new_information_indicates_no_content_found(self):
        self.state.new_information = "Could not retrieve or find content for any of the selected sources."

        self.research_loop._extract_entities_and_relations()

        self.mock_llm_client_instance.generate_text.assert_not_called()
        self.assertEqual(self.state.knowledge_graph_nodes, [])
        self.assertEqual(self.state.knowledge_graph_edges, [])

    def test_llm_returns_empty_json_object(self):
        self.state.new_information = "Some relevant text."
        self.mock_llm_client_instance.generate_text.return_value = '{}'

        self.research_loop._extract_entities_and_relations()

        self.mock_llm_client_instance.generate_text.assert_called_once()
        self.assertEqual(self.state.knowledge_graph_nodes, [])
        self.assertEqual(self.state.knowledge_graph_edges, [])

    def test_llm_returns_json_with_empty_node_edge_lists(self):
        self.state.new_information = "Text that might not have entities."
        self.mock_llm_client_instance.generate_text.return_value = '{"nodes": [], "edges": []}'

        self.research_loop._extract_entities_and_relations()

        self.mock_llm_client_instance.generate_text.assert_called_once()
        self.assertEqual(self.state.knowledge_graph_nodes, [])
        self.assertEqual(self.state.knowledge_graph_edges, [])

    def test_llm_response_has_extra_text_around_json(self):
        self.state.new_information = "Alice is a person."
        expected_nodes = [{"id": "alice", "label": "Alice", "type": "Person"}]
        json_payload = f'{{"nodes": {expected_nodes!r}, "edges": []}}'.replace("'", '"')
        self.mock_llm_client_instance.generate_text.return_value = f"Sure, here is the JSON you requested:\n```json\n{json_payload}\n```\nI hope this helps!"

        self.research_loop._extract_entities_and_relations()

        self.mock_llm_client_instance.generate_text.assert_called_once()
        self.assertEqual(self.state.knowledge_graph_nodes, expected_nodes)
        self.assertEqual(self.state.knowledge_graph_edges, [])


@patch('deep_research_project.core.research_loop.split_text_into_chunks')
class TestResearchLoopSummarizeSources(unittest.TestCase):
    def setUp(self):
        self.mock_config = MagicMock(spec=Configuration)
        self.mock_config.LLM_PROVIDER = "placeholder_llm"
        self.mock_config.LOG_LEVEL = "DEBUG"
        self.mock_config.OPENAI_API_KEY = None
        self.mock_config.OLLAMA_BASE_URL = None
        self.mock_config.MAX_SEARCH_RESULTS_PER_QUERY = 3
        self.mock_config.LLM_MAX_TOKENS = 1024
        self.mock_config.INTERACTIVE_MODE = False
        # New config values for chunking
        self.mock_config.SUMMARIZATION_CHUNK_SIZE_CHARS = 100 # Small for testing
        self.mock_config.SUMMARIZATION_CHUNK_OVERLAP_CHARS = 10 # Small for testing

        self.state = ResearchState(research_topic="Summarization Test Topic")
        self.state.current_query = "Test query for summarization"

        self.mock_llm_client_instance = MagicMock(spec=LLMClient)
        self.llm_client_patcher = patch('deep_research_project.core.research_loop.LLMClient', return_value=self.mock_llm_client_instance)
        self.MockLLMClient = self.llm_client_patcher.start()
        self.addCleanup(self.llm_client_patcher.stop)

        self.mock_search_client_instance = MagicMock()
        self.search_client_patcher = patch('deep_research_project.core.research_loop.SearchClient', return_value=self.mock_search_client_instance)
        self.MockSearchClient = self.search_client_patcher.start()
        self.addCleanup(self.search_client_patcher.stop)

        self.mock_content_retriever_instance = MagicMock()
        # Mock retrieve_and_extract to return content directly
        self.mock_content_retriever_instance.retrieve_and_extract.return_value = "Full text for source 1. " * 10 # Make it > chunk_size
        self.content_retriever_patcher = patch('deep_research_project.core.research_loop.ContentRetriever', return_value=self.mock_content_retriever_instance)
        self.MockContentRetriever = self.content_retriever_patcher.start()
        self.addCleanup(self.content_retriever_patcher.stop)

        # Mock _extract_entities_and_relations as it's called at the end of _summarize_sources
        self.extract_entities_patcher = patch.object(ResearchLoop, '_extract_entities_and_relations', return_value=None)
        self.mock_extract_entities = self.extract_entities_patcher.start()
        self.addCleanup(self.extract_entities_patcher.stop)

        self.research_loop = ResearchLoop(config=self.mock_config, state=self.state)
        # Initialize fetched_content as _summarize_sources expects it
        self.state.fetched_content = {}


    def test_successful_chunked_summarization_one_source_two_chunks(self, mock_split_text_into_chunks):
        selected_results = [SearchResult(title="Source 1", link="http://s1.com", snippet="")]
        self.state.fetched_content["http://s1.com"] = "Chunk one content. Chunk two content a bit longer."

        mock_split_text_into_chunks.return_value = ["Chunk one content.", "Chunk two content a bit longer."]

        self.mock_llm_client_instance.generate_text.side_effect = [
            "Summary of chunk1.",
            "Summary of chunk2.",
            "Final consolidated summary."
        ]

        self.research_loop._summarize_sources(selected_results)

        self.assertEqual(self.mock_llm_client_instance.generate_text.call_count, 3)

        # Check first call (chunk1 summary)
        args_chunk1, _ = self.mock_llm_client_instance.generate_text.call_args_list[0]
        self.assertIn("Chunk one content.", args_chunk1[0]['prompt']) # prompt is a kwarg
        self.assertIn(self.state.current_query, args_chunk1[0]['prompt'])

        # Check second call (chunk2 summary)
        args_chunk2, _ = self.mock_llm_client_instance.generate_text.call_args_list[1]
        self.assertIn("Chunk two content a bit longer.", args_chunk2[0]['prompt'])

        # Check third call (consolidation)
        args_consolidation, _ = self.mock_llm_client_instance.generate_text.call_args_list[2]
        self.assertIn("Summary of chunk1.", args_consolidation[0]['prompt'])
        self.assertIn("Summary of chunk2.", args_consolidation[0]['prompt'])

        self.assertEqual(self.state.new_information, "Final consolidated summary.")
        self.assertFalse(self.state.pending_source_selection)
        self.assertIn("Final consolidated summary.", self.state.accumulated_summary)
        self.mock_extract_entities.assert_called_once()


    def test_one_chunk_summarization_fails_empty_string(self, mock_split_text_into_chunks):
        selected_results = [SearchResult(title="Source 1", link="http://s1.com", snippet="")]
        self.state.fetched_content["http://s1.com"] = "Content for two chunks."
        mock_split_text_into_chunks.return_value = ["Chunk1 text", "Chunk2 text"]

        self.mock_llm_client_instance.generate_text.side_effect = [
            "",  # Chunk 1 summary fails (empty string)
            "Summary of chunk2.",
            "Final summary from chunk2." # Consolidation with only chunk2's summary
        ]

        self.research_loop._summarize_sources(selected_results)

        self.assertEqual(self.mock_llm_client_instance.generate_text.call_count, 3)
        self.assertEqual(self.state.new_information, "Final summary from chunk2.")
        self.assertIn("Summary of chunk2.", self.mock_llm_client_instance.generate_text.call_args_list[2].kwargs['prompt'])
        self.assertNotIn("Chunk1 text", self.mock_llm_client_instance.generate_text.call_args_list[2].kwargs['prompt']) # Assuming "" is not added
        self.assertFalse(self.state.pending_source_selection)
        self.mock_extract_entities.assert_called_once()


    def test_all_chunk_summarizations_fail(self, mock_split_text_into_chunks):
        selected_results = [SearchResult(title="Source 1", link="http://s1.com", snippet="")]
        self.state.fetched_content["http://s1.com"] = "Content for two chunks."
        mock_split_text_into_chunks.return_value = ["Chunk1 text", "Chunk2 text"]

        self.mock_llm_client_instance.generate_text.side_effect = [
            "",  # Chunk 1 summary fails
            None # Chunk 2 summary fails (None also treated as empty)
        ] # No call for consolidation if all_chunk_summaries is empty

        self.research_loop._summarize_sources(selected_results)

        self.assertEqual(self.mock_llm_client_instance.generate_text.call_count, 2) # Only two chunk summary attempts
        self.assertEqual(self.state.new_information, "No content could be summarized from the selected sources.")
        self.assertFalse(self.state.pending_source_selection)
        self.mock_extract_entities.assert_called_once() # Should still be called


    def test_final_consolidation_fails(self, mock_split_text_into_chunks):
        selected_results = [SearchResult(title="Source 1", link="http://s1.com", snippet="")]
        self.state.fetched_content["http://s1.com"] = "Content for two chunks."
        mock_split_text_into_chunks.return_value = ["Chunk1 text", "Chunk2 text"]

        self.mock_llm_client_instance.generate_text.side_effect = [
            "Summary of chunk1.",
            "Summary of chunk2.",
            Exception("LLM error during consolidation") # Consolidation fails
        ]

        self.research_loop._summarize_sources(selected_results)

        self.assertEqual(self.mock_llm_client_instance.generate_text.call_count, 3)
        self.assertEqual(self.state.new_information, "Error occurred during final summary consolidation.")
        self.assertFalse(self.state.pending_source_selection)
        self.mock_extract_entities.assert_called_once()

    def test_no_sources_selected(self, mock_split_text_into_chunks):
        # This case is handled before fetching/chunking loop
        self.research_loop._summarize_sources(selected_results=[])

        mock_split_text_into_chunks.assert_not_called()
        self.mock_llm_client_instance.generate_text.assert_not_called()
        self.assertEqual(self.state.new_information, "No sources were selected for summarization.")
        # self.state.pending_source_selection will be False due to the finally block,
        # but it might be set to False even before that by the early return.
        # self.mock_extract_entities.assert_called_once() # _extract_entities_and_relations is NOT called if no selected_results (early return)

    def test_no_content_to_chunk_for_selected_source(self, mock_split_text_into_chunks):
        selected_results = [SearchResult(title="Source 1", link="http://s1.com", snippet="")]
        self.state.fetched_content["http://s1.com"] = "" # Empty content

        # split_text_into_chunks would return [] for empty string, so LLM not called for chunk summaries
        mock_split_text_into_chunks.return_value = []

        self.research_loop._summarize_sources(selected_results)

        mock_split_text_into_chunks.assert_called_once_with("", self.mock_config.SUMMARIZATION_CHUNK_SIZE_CHARS, self.mock_config.SUMMARIZATION_CHUNK_OVERLAP_CHARS)
        self.mock_llm_client_instance.generate_text.assert_not_called() # No chunk summaries, no consolidation
        self.assertEqual(self.state.new_information, "No content could be summarized from the selected sources.")
        self.assertFalse(self.state.pending_source_selection)
        self.mock_extract_entities.assert_called_once()

    def test_split_text_raises_valueerror(self, mock_split_text_into_chunks):
        selected_results = [SearchResult(title="Source 1", link="http://s1.com", snippet="")]
        self.state.fetched_content["http://s1.com"] = "Some text that would cause split_text_into_chunks to fail."
        mock_split_text_into_chunks.side_effect = ValueError("Test error from splitter")

        self.research_loop._summarize_sources(selected_results)

        mock_split_text_into_chunks.assert_called_once()
        self.mock_llm_client_instance.generate_text.assert_not_called() # Should skip to end if no chunks
        self.assertEqual(self.state.new_information, "No content could be summarized from the selected sources.")
        self.mock_extract_entities.assert_called_once()


if __name__ == '__main__':
    unittest.main(argv=['first-arg-is-ignored'], exit=False)
