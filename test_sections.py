import asyncio
from unittest.mock import MagicMock, AsyncMock
from deep_research_project.core.research_loop import ResearchLoop
from deep_research_project.core.state import ResearchState, ResearchPlanModel, Section, KnowledgeGraphModel, KGNode
from deep_research_project.config.config import Configuration

def create_mock_config():
    config = MagicMock()
    config.LLM_PROVIDER = "placeholder_llm"
    config.SEARCH_API = "duckduckgo"
    config.INTERACTIVE_MODE = False
    config.MAX_RESEARCH_LOOPS = 1
    config.MAX_SEARCH_RESULTS_PER_QUERY = 1
    config.SUMMARIZATION_CHUNK_SIZE_CHARS = 1000
    config.SUMMARIZATION_CHUNK_OVERLAP_CHARS = 100
    config.PROCESS_PDF_FILES = True
    config.LOG_LEVEL = "INFO"
    return config

async def test_multiple_sections():
    print("Testing multiple sections...")
    config = create_mock_config()
    state = ResearchState("Test Topic")
    loop = ResearchLoop(config, state)

    # Mock LLM to return a 3-section plan
    loop.llm_client.generate_structured = AsyncMock(side_effect=[
        ResearchPlanModel(sections=[
            Section(title="S1", description="D1"),
            Section(title="S2", description="D2"),
            Section(title="S3", description="D3")
        ]),
        KnowledgeGraphModel(nodes=[], edges=[]),
        KnowledgeGraphModel(nodes=[], edges=[]),
        KnowledgeGraphModel(nodes=[], edges=[])
    ])
    loop.llm_client.generate_text = AsyncMock(return_value="Some summary text long enough for KG extraction.")
    loop.search_client.search = AsyncMock(return_value=[{"title": "T1", "link": "L1", "snippet": "S1"}])
    loop.content_retriever.retrieve_and_extract = AsyncMock(return_value="Content")

    await loop.run_loop()

    print(f"Final section index: {state.current_section_index}")
    for i, sec in enumerate(state.research_plan):
        print(f"Section {i} status: {sec['status']}")
        assert sec['status'] == 'completed', f"Section {i} was not completed!"

    assert state.current_section_index == 3
    print("Multiple sections test passed.")

if __name__ == "__main__":
    asyncio.run(test_multiple_sections())
