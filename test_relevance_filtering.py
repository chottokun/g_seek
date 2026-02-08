#!/usr/bin/env python
"""
Simple integration test for relevance filtering feature.
Tests the basic functionality without making actual API calls.
"""
import asyncio
from deep_research_project.config.config import Configuration
from deep_research_project.core.state import SearchResult, ResearchState
from deep_research_project.tools.llm_client import LLMClient
from deep_research_project.tools.search_client import SearchClient
from deep_research_project.tools.content_retriever import ContentRetriever
from deep_research_project.core.execution import ResearchExecutor
from deep_research_project.core.planning import ResearchPlanner

async def test_relevance_filtering_config():
    """Test that relevance filtering configuration is loaded correctly."""
    print("Test 1: Configuration Loading")
    config = Configuration()
    assert config.ENABLE_RELEVANCE_FILTERING == True, "Relevance filtering should be enabled by default"
    assert config.RELEVANCE_FILTER_MODE == "snippet", "Default mode should be 'snippet'"
    assert config.RELEVANCE_THRESHOLD == 0.6, "Default threshold should be 0.6"
    assert config.MAX_RELEVANT_RESULTS == 5, "Default max results should be 5"
    assert config.ENABLE_QUERY_REGENERATION == True, "Query regeneration should be enabled by default"
    print("✓ Configuration loaded correctly")

def test_search_result_model():
    """Test that SearchResult model has relevance_score field."""
    print("\nTest 2: SearchResult Model")
    result = SearchResult(
        title="Test Title",
        link="https://example.com",
        snippet="Test snippet",
        relevance_score=0.8
    )
    assert result.relevance_score == 0.8, "Relevance score should be set"
    print("✓ SearchResult model extended correctly")

def test_research_state_regenerated_queries():
    """Test that ResearchState has regenerated_queries field."""
    print("\nTest 3: ResearchState Model")
    state = ResearchState(research_topic="Test Topic", language="Japanese")
    assert hasattr(state, 'regenerated_queries'), "ResearchState should have regenerated_queries field"
    assert isinstance(state.regenerated_queries, set), "regenerated_queries should be a set"
    assert len(state.regenerated_queries) == 0, "regenerated_queries should be empty initially"
    
    # Test adding queries
    state.regenerated_queries.add("query1")
    state.regenerated_queries.add("query2")
    assert len(state.regenerated_queries) == 2, "Should have 2 queries"
    assert "query1" in state.regenerated_queries, "query1 should be in set"
    print("✓ ResearchState extended correctly")

async def test_executor_methods_exist():
    """Test that ResearchExecutor has new methods."""
    print("\nTest 4: ResearchExecutor Methods")
    config = Configuration()
    llm_client = LLMClient(config)
    search_client = SearchClient(config)
    content_retriever = ContentRetriever(config)
    executor = ResearchExecutor(config, llm_client, search_client, content_retriever)
    
    assert hasattr(executor, 'score_relevance'), "Executor should have score_relevance method"
    assert hasattr(executor, 'filter_by_relevance'), "Executor should have filter_by_relevance method"
    assert callable(executor.score_relevance), "score_relevance should be callable"
    assert callable(executor.filter_by_relevance), "filter_by_relevance should be callable"
    print("✓ ResearchExecutor methods exist")

async def test_planner_regenerate_query_exists():
    """Test that ResearchPlanner has regenerate_query method."""
    print("\nTest 5: ResearchPlanner Methods")
    config = Configuration()
    llm_client = LLMClient(config)
    planner = ResearchPlanner(config, llm_client)
    
    assert hasattr(planner, 'regenerate_query'), "Planner should have regenerate_query method"
    assert callable(planner.regenerate_query), "regenerate_query should be callable"
    print("✓ ResearchPlanner methods exist")

async def main():
    """Run all tests."""
    print("=" * 60)
    print("Relevance Filtering Feature - Integration Tests")
    print("=" * 60)
    
    try:
        # Synchronous tests
        await test_relevance_filtering_config()
        test_search_result_model()
        test_research_state_regenerated_queries()
        
        # Async tests
        await test_executor_methods_exist()
        await test_planner_regenerate_query_exists()
        
        print("\n" + "=" * 60)
        print("✓ All tests passed!")
        print("=" * 60)
        return 0
    except AssertionError as e:
        print(f"\n✗ Test failed: {e}")
        return 1
    except Exception as e:
        print(f"\n✗ Unexpected error: {e}")
        import traceback
        traceback.print_exc()
        return 1

if __name__ == "__main__":
    exit_code = asyncio.run(main())
    exit(exit_code)
