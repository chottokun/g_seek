import asyncio
import logging
import sys
from deep_research_project.config.config import Configuration
from deep_research_project.tools.llm_client import LLMClient
from deep_research_project.tools.search_client import SearchClient
from deep_research_project.tools.content_retriever import ContentRetriever
from deep_research_project.core.graph import create_research_graph

# Configure logging to see the flow
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

async def main():
    logger.info("Starting End-to-End Deep Agent Graph Test with real LLM")
    
    config = Configuration()
    llm_client = LLMClient(config)
    search_client = SearchClient(config)
    content_retriever = ContentRetriever(config)
    
    # Initialize Graph
    graph = create_research_graph(config, llm_client, search_client, content_retriever)
    
    # Initial State
    initial_state = {
        "topic": "Latest trends in AI Agents 2024",
        "language": "Japanese",
        "plan": [],
        "current_section_index": -1,
        "findings": [],
        "sources": [],
        "knowledge_graph": {"nodes": [], "edges": []},
        "research_context": [],
        "is_complete": False,
        "iteration_count": 0,
        "max_iterations": 5 # Reduce for testing
    }
    
    try:
        logger.info(f"Invoking graph for topic: {initial_state['topic']}")
        result = await graph.ainvoke(initial_state)
        
        logger.info("--- TEST RESULT SUMMARY ---")
        logger.info(f"Is Complete: {result['is_complete']}")
        logger.info(f"Iteration Count: {result['iteration_count']}")
        logger.info(f"Plan Sections: {len(result['plan'])}")
        logger.info(f"Findings gathered: {len(result['findings'])}")
        
        for i, finding in enumerate(result['findings']):
            # Use truncation as requested by user for logs
            safe_finding = (finding[:200] + "...") if len(finding) > 200 else finding
            logger.info(f"Finding {i+1}: {safe_finding}")
            
    except Exception as e:
        logger.error(f"Test failed with error: {e}", exc_info=True)
        sys.exit(1)

if __name__ == "__main__":
    asyncio.run(main())
