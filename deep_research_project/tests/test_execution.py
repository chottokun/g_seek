import unittest
import asyncio
from unittest.mock import MagicMock, AsyncMock, patch
from typing import List

from deep_research_project.core.execution import ResearchExecutor
from deep_research_project.config.config import Configuration
from deep_research_project.tools.llm_client import LLMClient
from deep_research_project.tools.search_client import SearchClient
from deep_research_project.tools.content_retriever import ContentRetriever
from deep_research_project.core.state import SearchResult

class TestResearchExecutor(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.mock_config = MagicMock(spec=Configuration)
        self.mock_config.MAX_CONCURRENT_CHUNKS = 5
        self.mock_config.MAX_CONCURRENT_RETRIEVALS = 5
        self.mock_config.USE_SNIPPETS_ONLY_MODE = False
        self.mock_config.SUMMARIZATION_CHUNK_SIZE_CHARS = 100
        self.mock_config.SUMMARIZATION_CHUNK_OVERLAP_CHARS = 10
        self.mock_config.BATCH_SIZE_RELEVANCE = 5
        self.mock_config.RELEVANCE_THRESHOLD = 0.4
        self.mock_config.MAX_RELEVANT_RESULTS = 5

        self.mock_llm_client = MagicMock(spec=LLMClient)
        self.mock_search_client = MagicMock(spec=SearchClient)
        self.mock_content_retriever = MagicMock(spec=ContentRetriever)

        self.executor = ResearchExecutor(
            self.mock_config,
            self.mock_llm_client,
            self.mock_search_client,
            self.mock_content_retriever
        )

    async def test_search(self):
        mock_results = [SearchResult(title="Result 1", link="http://example.com/1", snippet="Snippet 1")]
        self.mock_search_client.search = AsyncMock(return_value=mock_results)

        results = await self.executor.search("test query", num_results=10)

        self.assertEqual(results, mock_results)
        self.mock_search_client.search.assert_called_once_with("test query", num_results=10)

    async def test_retrieve_and_summarize_success(self):
        results = [
            SearchResult(title="R1", link="http://r1.com", snippet="S1"),
            SearchResult(title="R2", link="http://r2.com", snippet="S2")
        ]
        query = "test query"
        language = "English"

        self.mock_content_retriever.retrieve_and_extract = AsyncMock(side_effect=["Content 1", "Content 2"])
        # Mocking llm_client.generate_text for both chunk summarization and final synthesis
        # 2 results -> 2 calls for chunks (if they fit in one chunk each), 1 for synthesis
        self.mock_llm_client.generate_text = AsyncMock(side_effect=["Summary 1", "Summary 2", "Final Synthesis"])

        summary = await self.executor.retrieve_and_summarize(results, query, language)

        self.assertEqual(summary, "Final Synthesis")
        self.assertEqual(self.mock_content_retriever.retrieve_and_extract.call_count, 2)
        # 2 summaries + 1 final synthesis = 3 calls
        self.assertEqual(self.mock_llm_client.generate_text.call_count, 3)

    async def test_retrieve_and_summarize_snippets_only(self):
        self.mock_config.USE_SNIPPETS_ONLY_MODE = True
        results = [SearchResult(title="R1", link="http://r1.com", snippet="Snippet content")]

        self.mock_llm_client.generate_text = AsyncMock(side_effect=["Chunk Summary", "Final Summary"])

        summary = await self.executor.retrieve_and_summarize(results, "query", "English")

        self.assertEqual(summary, "Final Summary")
        self.mock_content_retriever.retrieve_and_extract.assert_not_called()

    async def test_retrieve_and_summarize_no_content(self):
        results = [SearchResult(title="R1", link="http://r1.com", snippet="S1")]
        self.mock_content_retriever.retrieve_and_extract = AsyncMock(return_value="")
        # In this case it falls back to snippet if no content
        self.mock_llm_client.generate_text = AsyncMock(side_effect=["Chunk Summary", "Final Summary"])

        summary = await self.executor.retrieve_and_summarize(results, "query", "English")
        self.assertEqual(summary, "Final Summary")

    async def test_retrieve_and_summarize_chunk_failures(self):
        results = [SearchResult(title="R1", link="http://r1.com", snippet="S1")]
        self.mock_content_retriever.retrieve_and_extract = AsyncMock(return_value="Some content")
        # Fail chunk summarization
        self.mock_llm_client.generate_text = AsyncMock(side_effect=Exception("LLM Error"))

        summary = await self.executor.retrieve_and_summarize(results, "query", "English")
        self.assertEqual(summary, "Failed to generate any summaries from the segments.")

    async def test_retrieve_and_summarize_progress_callback(self):
        results = [SearchResult(title="R1", link="http://r1.com", snippet="S1")]
        self.mock_content_retriever.retrieve_and_extract = AsyncMock(return_value="Content")
        self.mock_llm_client.generate_text = AsyncMock(side_effect=["Summary", "Final"])

        progress_callback = AsyncMock()
        await self.executor.retrieve_and_summarize(results, "query", "English", progress_callback=progress_callback)

        # Should be called for retrieval and summarization
        self.assertTrue(progress_callback.called)

    async def test_retrieve_and_summarize_defensive_string_conversion(self):
        results = [SearchResult(title="R1", link="http://r1.com", snippet="S1")]
        self.mock_content_retriever.retrieve_and_extract = AsyncMock(return_value="Content")
        # LLM returns a list or something else
        self.mock_llm_client.generate_text = AsyncMock(side_effect=[["Summary Part 1", "Part 2"], "Final"])

        summary = await self.executor.retrieve_and_summarize(results, "query", "English")
        self.assertEqual(summary, "Final")
        # Ensure it didn't crash and processed the list
        self.assertEqual(self.mock_llm_client.generate_text.call_count, 2)

    async def test_score_relevance_success(self):
        result = SearchResult(title="T1", link="L1", snippet="S1")
        self.mock_llm_client.generate_text = AsyncMock(return_value="0.8")

        score = await self.executor.score_relevance("query", result, "English")
        self.assertEqual(score, 0.8)

    async def test_score_relevance_parse_failure(self):
        result = SearchResult(title="T1", link="L1", snippet="S1")
        self.mock_llm_client.generate_text = AsyncMock(return_value="not a number")

        score = await self.executor.score_relevance("query", result, "English")
        self.assertEqual(score, 0.5) # Default

    async def test_score_relevance_attribute_error(self):
        result = SearchResult(title="T1", link="L1", snippet="S1")
        # Returning None will cause .strip() to raise AttributeError
        self.mock_llm_client.generate_text = AsyncMock(return_value=None)

        score = await self.executor.score_relevance("query", result, "English")
        self.assertEqual(score, 0.5)

    async def test_score_relevance_index_error(self):
        result = SearchResult(title="T1", link="L1", snippet="S1")
        # Empty string (after strip) will cause split()[0] to raise IndexError
        self.mock_llm_client.generate_text = AsyncMock(return_value="   ")

        score = await self.executor.score_relevance("query", result, "English")
        self.assertEqual(score, 0.5)

    async def test_score_relevance_value_error(self):
        result = SearchResult(title="T1", link="L1", snippet="S1")
        # Non-numeric string will cause float() to raise ValueError
        self.mock_llm_client.generate_text = AsyncMock(return_value="not-a-number")

        score = await self.executor.score_relevance("query", result, "English")
        self.assertEqual(score, 0.5)

    async def test_score_relevance_batch_success(self):
        results = [
            SearchResult(title="T1", link="L1", snippet="S1"),
            SearchResult(title="T2", link="L2", snippet="S2")
        ]
        mock_batch_response = MagicMock()
        mock_batch_response.scores = [0.9, 0.1]
        self.mock_llm_client.generate_structured = AsyncMock(return_value=mock_batch_response)

        scores = await self.executor.score_relevance_batch("query", results, "English")
        self.assertEqual(scores, [0.9, 0.1])

    async def test_score_relevance_batch_empty(self):
        scores = await self.executor.score_relevance_batch("query", [], "English")
        self.assertEqual(scores, [])
        self.mock_llm_client.generate_structured.assert_not_called()

    async def test_score_relevance_batch_japanese(self):
        results = [SearchResult(title="T1", link="L1", snippet="S1")]
        mock_batch_response = MagicMock()
        mock_batch_response.scores = [0.9]
        self.mock_llm_client.generate_structured = AsyncMock(return_value=mock_batch_response)

        await self.executor.score_relevance_batch("クエリ", results, "Japanese")

        # Check that Japanese keywords are in the prompt
        args, kwargs = self.mock_llm_client.generate_structured.call_args
        prompt = args[0]
        self.assertIn("クエリ", prompt)
        self.assertIn("関連性", prompt)

    async def test_score_relevance_batch_clamping(self):
        results = [
            SearchResult(title="T1", link="L1", snippet="S1"),
            SearchResult(title="T2", link="L2", snippet="S2")
        ]
        mock_batch_response = MagicMock()
        mock_batch_response.scores = [1.5, -0.5]
        self.mock_llm_client.generate_structured = AsyncMock(return_value=mock_batch_response)

        scores = await self.executor.score_relevance_batch("query", results, "English")
        self.assertEqual(scores, [1.0, 0.0])

    async def test_score_relevance_batch_padding(self):
        results = [
            SearchResult(title="T1", link="L1", snippet="S1"),
            SearchResult(title="T2", link="L2", snippet="S2")
        ]
        mock_batch_response = MagicMock()
        mock_batch_response.scores = [0.9] # Only one score for two results
        self.mock_llm_client.generate_structured = AsyncMock(return_value=mock_batch_response)

        scores = await self.executor.score_relevance_batch("query", results, "English")
        self.assertEqual(scores, [0.9, 0.5])

    async def test_score_relevance_batch_truncation(self):
        results = [SearchResult(title="T1", link="L1", snippet="S1")]
        mock_batch_response = MagicMock()
        mock_batch_response.scores = [0.9, 0.1] # Two scores for one result
        self.mock_llm_client.generate_structured = AsyncMock(return_value=mock_batch_response)

        scores = await self.executor.score_relevance_batch("query", results, "English")
        self.assertEqual(scores, [0.9])

    async def test_score_relevance_batch_fallback(self):
        results = [
            SearchResult(title="T1", link="L1", snippet="S1"),
            SearchResult(title="T2", link="L2", snippet="S2")
        ]
        self.mock_llm_client.generate_structured = AsyncMock(side_effect=Exception("Batch error"))
        self.mock_llm_client.generate_text = AsyncMock(side_effect=["0.7", "0.3"])

        scores = await self.executor.score_relevance_batch("query", results, "English")
        self.assertEqual(scores, [0.7, 0.3])
        self.assertEqual(self.mock_llm_client.generate_text.call_count, 2)

    async def test_filter_by_relevance_success(self):
        results = [
            SearchResult(title="High", link="H", snippet="S1"),
            SearchResult(title="Low", link="L", snippet="S2"),
            SearchResult(title="Mid", link="M", snippet="S3")
        ]
        # Mock batch response
        mock_batch_response = MagicMock()
        mock_batch_response.scores = [0.9, 0.1, 0.5]
        self.mock_llm_client.generate_structured = AsyncMock(return_value=mock_batch_response)

        # Threshold is 0.4 by default in asyncSetUp
        filtered = await self.executor.filter_by_relevance("query", results, "English")

        self.assertEqual(len(filtered), 2)
        self.assertEqual(filtered[0].title, "High")
        self.assertEqual(filtered[1].title, "Mid")
        self.assertEqual(filtered[0].relevance_score, 0.9)

    async def test_filter_by_relevance_custom_threshold(self):
        results = [
            SearchResult(title="High", link="H", snippet="S1"),
            SearchResult(title="Mid", link="M", snippet="S2")
        ]
        mock_batch_response = MagicMock()
        mock_batch_response.scores = [0.9, 0.5]
        self.mock_llm_client.generate_structured = AsyncMock(return_value=mock_batch_response)

        # Custom threshold 0.8
        filtered = await self.executor.filter_by_relevance("query", results, "English", threshold=0.8)

        self.assertEqual(len(filtered), 1)
        self.assertEqual(filtered[0].title, "High")

    async def test_filter_by_relevance_batching(self):
        self.mock_config.BATCH_SIZE_RELEVANCE = 2
        results = [
            SearchResult(title="R1", link="L1", snippet="S1"),
            SearchResult(title="R2", link="L2", snippet="S2"),
            SearchResult(title="R3", link="L3", snippet="S3")
        ]
        mock_response1 = MagicMock()
        mock_response1.scores = [0.9, 0.8]
        mock_response2 = MagicMock()
        mock_response2.scores = [0.7]

        self.mock_llm_client.generate_structured = AsyncMock(side_effect=[mock_response1, mock_response2])

        filtered = await self.executor.filter_by_relevance("query", results, "English")

        self.assertEqual(len(filtered), 3)
        self.assertEqual(self.mock_llm_client.generate_structured.call_count, 2)

    async def test_filter_by_relevance_empty(self):
        filtered = await self.executor.filter_by_relevance("query", [], "English")
        self.assertEqual(filtered, [])

    async def test_filter_by_relevance_sorting(self):
        results = [
            SearchResult(title="Low", link="L", snippet="S1"),
            SearchResult(title="High", link="H", snippet="S2"),
            SearchResult(title="Mid", link="M", snippet="S3")
        ]
        mock_batch_response = MagicMock()
        mock_batch_response.scores = [0.5, 0.9, 0.7]
        self.mock_llm_client.generate_structured = AsyncMock(return_value=mock_batch_response)

        filtered = await self.executor.filter_by_relevance("query", results, "English")

        self.assertEqual(len(filtered), 3)
        self.assertEqual(filtered[0].title, "High")
        self.assertEqual(filtered[1].title, "Mid")
        self.assertEqual(filtered[2].title, "Low")

if __name__ == "__main__":
    unittest.main()
