import unittest
import asyncio
import os
from unittest.mock import MagicMock, AsyncMock, patch
from deep_research_project.config.config import Configuration
from deep_research_project.core.research_loop import ResearchLoop
from deep_research_project.core.state import ResearchState, SearchResult, KnowledgeGraphModel

class TestResearchLoopParallel(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        with patch.dict('os.environ', {
            'LLM_PROVIDER': 'placeholder_llm',
            'MAX_CONCURRENT_CHUNKS': '2',
            'LLM_RATE_LIMIT_RPM': '0',
            'SUMMARIZATION_CHUNK_SIZE_CHARS': '10',
            'SUMMARIZATION_CHUNK_OVERLAP_CHARS': '0',
            'USE_SNIPPETS_ONLY_MODE': 'True'
        }):
            self.config = Configuration()

        self.state = ResearchState(research_topic="Test")
        self.state.language = "English"
        self.state.current_query = "Test Query"

        self.loop = ResearchLoop(self.config, self.state)

    async def test_parallel_summarization(self):
        # We have 4 chunks, and MAX_CONCURRENT_CHUNKS = 2
        # Each chunk summary takes 0.5s
        # Total time should be ~1.0s if parallelized (2 waves of 2)
        # If sequential, it would be 2.0s

        selected = [
            SearchResult(title="T1", link="L1", snippet="12345678901234567890") # 2 chunks of 10
        ]

        call_count = 0
        async def mock_generate_text(prompt, **kwargs):
            nonlocal call_count
            call_count += 1
            await asyncio.sleep(0.5)
            return f"Summary {call_count}"

        self.loop.llm_client.generate_text = AsyncMock(side_effect=mock_generate_text)

        start_time = asyncio.get_event_loop().time()
        await self.loop._summarize_sources(selected)
        end_time = asyncio.get_event_loop().time()

        duration = end_time - start_time
        # 2 chunks -> 1 wave of 2 if parallel -> 0.5s
        # Wait, I said 2 chunks. Let's make it 4 chunks.
        # Snippet is 20 chars, chunk size is 10. That's 2 chunks.
        # Let's make snippet 40 chars.

        # Reset and try with 4 chunks
        call_count = 0
        selected = [
            SearchResult(title="T1", link="L1", snippet="1234567890123456789012345678901234567890") # 4 chunks
        ]
        start_time = asyncio.get_event_loop().time()
        await self.loop._summarize_sources(selected)
        end_time = asyncio.get_event_loop().time()

        duration = end_time - start_time
        # 4 chunks, concurrency 2 -> 2 waves of 0.5s -> ~1.0s
        self.assertGreaterEqual(duration, 1.0)
        self.assertLess(duration, 1.4)

    async def test_parallel_graph_and_reflection(self):
        self.state.new_information = "Some long enough text for KG extraction"

        async def mock_gen_struct(*args, **kwargs):
            await asyncio.sleep(0.5)
            return KnowledgeGraphModel(nodes=[], edges=[])

        async def mock_gen_text(*args, **kwargs):
            await asyncio.sleep(0.5)
            return "EVALUATION: CONCLUDE\nQUERY: None"

        self.loop.llm_client.generate_structured = AsyncMock(side_effect=mock_gen_struct)
        self.loop.llm_client.generate_text = AsyncMock(side_effect=mock_gen_text)

        start_time = asyncio.get_event_loop().time()
        # These two should run in parallel
        await asyncio.gather(
            self.loop._extract_entities_and_relations(),
            self.loop._reflect_on_summary()
        )
        end_time = asyncio.get_event_loop().time()

        duration = end_time - start_time
        # If parallel, ~0.5s. If sequential, ~1.0s.
        self.assertGreaterEqual(duration, 0.5)
        self.assertLess(duration, 0.8)

if __name__ == '__main__':
    unittest.main()
