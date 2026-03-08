import asyncio
import uuid
import logging
from deep_research_project.config.config import Configuration
from deep_research_project.tools.llm_client import LLMClient
from deep_research_project.core.graph import create_research_graph

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def test_hitl_flow():
    config = Configuration()
    llm_client = LLMClient(config)
    
    # Use mocks or real client depending on .env
    # For HITL verification, we just want to see the stop/resume behavior
    graph = create_research_graph(config, llm_client, None, None)
    
    thread_id = str(uuid.uuid4())
    graph_config = {"configurable": {"thread_id": thread_id}}
    
    initial_state = {
        "topic": "Future of AI Agents in 2025",
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
    
    logger.info("--- Step 1: Starting Graph (expecting interrupt before 'researcher') ---")
    
    # Run until interrupt
    # Note: async for loop will terminate when graph pauses
    async for event in graph.astream(initial_state, config=graph_config, stream_mode="updates"):
        for node_name, node_update in event.items():
            logger.info(f"Node completed: {node_name}")
            
    # Check state and next step
    state_snap = await graph.aget_state(graph_config)
    logger.info(f"Current next steps: {state_snap.next}")
    
    if "researcher" in state_snap.next:
        logger.info("SUCCESS: Graph correctly interrupted before 'researcher' node.")
        logger.info(f"Generated Plan length: {len(state_snap.values.get('plan', []))}")
        
        # Simulate User Approval and Resume
        logger.info("--- Step 2: Resuming Graph (simulating approval) ---")
        async for event in graph.astream(None, config=graph_config, stream_mode="updates"):
             for node_name, node_update in event.items():
                logger.info(f"Node completed: {node_name}")
        
        final_state = await graph.aget_state(graph_config)
        logger.info("Graph finished.")
        logger.info(f"Final is_complete: {final_state.values.get('is_complete')}")
    else:
        logger.error("FAILURE: Graph did not interrupt as expected.")

if __name__ == "__main__":
    asyncio.run(test_hitl_flow())
