import asyncio
import uuid
import logging
from deep_research_project.config.config import Configuration
from deep_research_project.tools.llm_client import LLMClient
from deep_research_project.core.graph import create_research_graph
from deep_research_project.core.skills_manager import SkillRegistry

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def test_orchestration_flow():
    config = Configuration()
    llm_client = LLMClient(config)
    
    # We need a real search client or mock for the fallback, 
    # but we want to test delegation.
    # Let's use real components but focus on the logs.
    from deep_research_project.tools.search_client import SearchClient
    from deep_research_project.tools.content_retriever import ContentRetriever
    search_client = SearchClient(config)
    content_retriever = ContentRetriever(config)
    
    graph = create_research_graph(config, llm_client, search_client, content_retriever)
    
    thread_id = str(uuid.uuid4())
    graph_config = {"configurable": {"thread_id": thread_id}}
    
    # We want to trigger 'arxiv-research'
    topic = "Recent breakthroughs in LLM architecture 2024"
    
    initial_state = {
        "topic": topic,
        "language": "English",
        "plan": [],
        "current_section_index": -1,
        "findings": [],
        "sources": [],
        "knowledge_graph": {"nodes": [], "edges": []},
        "research_context": [],
        "activated_skill_ids": [],
        "current_query": None,
        "is_complete": False,
        "iteration_count": 0,
        "max_iterations": 10
    }
    
    logger.info("--- Phase 1: Planning (expecting arxiv-research trigger) ---")
    async for event in graph.astream(initial_state, config=graph_config, stream_mode="updates"):
        for node_name, node_update in event.items():
            logger.info(f"Node completed: {node_name}")
            if node_name == "planner":
                logger.info(f"Activated Skills: {node_update.get('activated_skill_ids')}")

    # Check if we are interrupted at researcher
    state_snap = await graph.aget_state(graph_config)
    if "researcher" in state_snap.next:
        logger.info("HITL Interrupt caught. Resuming...")
        
        # Resume to see delegation in action
        async for event in graph.astream(None, config=graph_config, stream_mode="updates"):
            for node_name, node_update in event.items():
                logger.info(f"Node completed: {node_name}")
                if node_name == "researcher":
                    # If orchestration worked, findings should be from the sub-agent
                    logger.info("Researcher node finished. Checking if it was delegated.")
                    # We can't easily check 'delegated' from state alone without extra flags, 
                    # but logs should show 'Orchestrator: Delegating...'
                    
    logger.info("Orchestration verification test complete.")

if __name__ == "__main__":
    asyncio.run(test_orchestration_flow())
