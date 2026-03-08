import logging
import asyncio
from typing import Dict, List, Any, Optional
from langgraph.graph import StateGraph, END
from langgraph.checkpoint.memory import MemorySaver
from deep_research_project.core.graph_state import AgentState
from deep_research_project.core.skills_manager import SkillRegistry
from deep_research_project.config.config import Configuration
from deep_research_project.tools.llm_client import LLMClient
from deep_research_project.core.planning import ResearchPlanner
from deep_research_project.core.execution import ResearchExecutor
from deep_research_project.core.reflection import ResearchReflector
from deep_research_project.core.reporting import ResearchReporter

logger = logging.getLogger(__name__)

# --- Node Implementation ---

async def planner_node(state: AgentState, config: Configuration, planner: ResearchPlanner, skills_mgr: SkillRegistry):
    """Initial planning node. Consults SkillRegistry for dynamic discovery (SkillsMiddleware)."""
    logger.info(f"--- PLANNER NODE ---")
    
    # Progressive Disclosure: Get available skills metadata
    available_skills = skills_mgr.list_skills()
    
    # Prompt LLM to select relevant skills based on metadata
    selected_skill_ids = []
    if available_skills:
        skill_descriptions = "\n".join([f"- {s['id']}: {s['description']}" for s in available_skills])
        trigger_prompt = (
            f"Topic: {state['topic']}\n\n"
            f"Available Skills:\n{skill_descriptions}\n\n"
            "Based on the topic, which skills should be activated? "
            "Respond with a comma-separated list of skill IDs, or 'None' if no skills are relevant."
        )
        try:
            from deep_research_project.tools.llm_client import LLMClient
            # We assume planner has access to llm_client or we use one from config
            trigger_resp = await planner.llm_client.generate_text(trigger_prompt)
            if "none" not in trigger_resp.lower():
                selected_skill_ids = [s.strip() for s in trigger_resp.split(",") if s.strip() in skills_mgr.skills]
        except Exception as e:
            logger.error(f"Skill triggering failed: {e}")

    # Load full content of selected skills
    full_skills_context = []
    for sid in selected_skill_ids:
        skill = skills_mgr.get_skill(sid)
        if skill:
            full_skills_context.append(skill["content"])
            logger.info(f"Activated skill: {skill['name']}")

    state["research_context"] = full_skills_context
    
    # Enrich topic with full skill instructions
    context_str = "\n\n".join(full_skills_context)
    enriched_topic = f"{state['topic']}\n\n--- SKILLS GUIDANCE ---\n{context_str}" if full_skills_context else state["topic"]
    
    # Generate Research Plan
    plan = await planner.generate_plan(enriched_topic, state["language"])
    
    return {
        "plan": plan,
        "current_section_index": 0,
        "iteration_count": 0,
        "activated_skill_ids": selected_skill_ids,
        "current_query": None
    }

async def researcher_node(state: AgentState, config: Configuration, planner: ResearchPlanner, executor: ResearchExecutor, orchestrator: Any):
    """Execution node. Performs web search or delegates to specialized sub-agents."""
    idx = state["current_section_index"]
    
    # Boundary check to prevent IndexError
    if idx < 0 or idx >= len(state["plan"]):
        logger.warning(f"Researcher node called with invalid index {idx}. Plan length: {len(state['plan'])}")
        return {"is_complete": True}
        
    section = state["plan"][idx]
    logger.info(f"--- RESEARCHER NODE: {section['title']} ---")
    # Standard Web Search Workflow
    # Generate Query (only if no current_query provided by Reflector)
    query = state.get("current_query")
    if not query:
        query = await planner.generate_initial_query(
            topic=state["topic"],
            section_title=section["title"],
            section_description=section.get("description", ""),
            language=state["language"]
        )
    
    # Search
    results = await executor.search(query, getattr(config, "MAX_SEARCH_RESULTS_PER_QUERY", 3))
    
    # Filter
    relevant = await executor.filter_by_relevance(query, results, state["language"])
    
    # Retrieve & Summarize with TRUNCATION for logs
    summary = await executor.retrieve_and_summarize(relevant, query, state["language"])
    
    # Truncate for logging purposes if needed, but findings should stay intact
    safe_summary_log = (summary[:500] + '...') if len(summary) > 500 else summary
    logger.debug(f"Gathered summary (truncated for log): {safe_summary_log}")
    
    return {
        "findings": [summary],
        "sources": [{"title": r.title, "link": r.link} for r in relevant],
        "iteration_count": state["iteration_count"] + 1
    }

async def reflector_node(state: AgentState, config: Configuration, reflector: ResearchReflector):
    """Reflection node. Decides if more research is needed or moves to next section."""
    idx = state["current_section_index"]
    
    logger.info(f"--- REFLECTOR NODE ---")
    
    # Boundary check to prevent IndexError
    if idx < 0 or idx >= len(state["plan"]):
        logger.info("Reflector called at the end of plan or with invalid index.")
        return {"is_complete": True}
        
    section = state["plan"][idx]
    
    # Logic to decide next move: Reflect on current findings for THIS section
    # Note: findings is Annotated[operator.add], so we have all of them.
    # We pass the accumulated summary if possible, or recent findings.
    result = await reflector.reflect(
        topic=state["topic"],
        section_title=section["title"],
        section_description=section.get("description", ""),
        accumulated_summary="\n\n".join(state["findings"]),
        language=state["language"]
    )
    
    evaluation = result.get("evaluation", "CONCLUDE")
    next_query = result.get("query")
    
    if evaluation == "CONTINUE" and next_query and next_query.lower() != "none":
        logger.info(f"Reflector: Continuing research for section '{section['title']}' with new query: {next_query}")
        return {
            "current_query": next_query,
            "is_complete": False
        }
    else:
        logger.info(f"Reflector: Concluding section '{section['title']}'.")
        next_idx = idx + 1
        is_complete = next_idx >= len(state["plan"])
        return {
            "current_section_index": next_idx,
            "current_query": None, # Reset query for next section
            "is_complete": is_complete
        }

async def skills_extractor_node(state: AgentState, llm_client: LLMClient, skills_mgr: SkillRegistry):
    """Learns research expertise and generates or refines standardized SKILL.md documents."""
    logger.info(f"--- SKILLS EXTRACTOR NODE ---")
    
    from deep_research_project.core.prompts import (
        SKILLS_EXTRACTION_PROMPT_JA, SKILLS_EXTRACTION_PROMPT_EN,
        SKILLS_REFINEMENT_PROMPT_JA, SKILLS_REFINEMENT_PROMPT_EN
    )
    
    findings_str = "\n\n".join(state["findings"])[:4000]
    is_japanese = state["language"] == "Japanese"

    logger.info("Extracting insights to create a new dedicated domain skill...")
    prompt_tpl = SKILLS_EXTRACTION_PROMPT_JA if is_japanese else SKILLS_EXTRACTION_PROMPT_EN
    prompt = prompt_tpl.format(findings=findings_str)
    
    try:
        extraction = await llm_client.generate_text(prompt)
        patterns = [line.strip("- ").strip("* ").strip() for line in extraction.strip().split("\n") if line.strip()]
        
        if patterns:
            import re
            # Ensure unique ID for the specific topic domain
            base_id = re.sub(r'[^a-zA-Z0-9-]', '-', state["topic"].lower())[:30].strip("-")
            import uuid
            skill_id = f"domain-{base_id}-{uuid.uuid4().hex[:6]}"
            skill_name = f"Domain: {state['topic'][:30]}..."
            description = f"Dedicated parsing and methodological insights for researching: {state['topic']}. Trigger when exploring similar specific domains."
            
            content = "## Extracted Domain Instructions\n" + "\n".join([f"- {p}" for p in patterns])
            
            # Save as a distinct new skill
            skills_mgr.save_skill(skill_id, skill_name, description, content)
            logger.info(f"Extracted and saved NEW dedicated domain skill: {skill_id}")
            return {"newly_extracted_skill": skill_name}

    except Exception as e:
        logger.error(f"Failed to extract dedicated domain skill: {e}")
            
    return {"newly_extracted_skill": None}

# --- Graph Construction ---

def create_research_graph(config: Configuration, llm_client: LLMClient, search_client: Any, content_retriever: Any):
    # Initialize components
    from deep_research_project.core.skills_manager import SkillRegistry
    from deep_research_project.core.sub_agents import Orchestrator
    planner = ResearchPlanner(config, llm_client)
    executor = ResearchExecutor(config, llm_client, search_client, content_retriever)
    reflector = ResearchReflector(config, llm_client)
    skills_mgr = SkillRegistry()
    orchestrator = Orchestrator(skills_mgr, llm_client)
    
    workflow = StateGraph(AgentState)
    
    # Define Nodes with partial application for dependencies
    async def _planner_node(s): return await planner_node(s, config, planner, skills_mgr)
    async def _researcher_node(s): return await researcher_node(s, config, planner, executor, orchestrator)
    async def _reflector_node(s): return await reflector_node(s, config, reflector)
    async def _skills_extractor_node(s): return await skills_extractor_node(s, llm_client, skills_mgr)

    workflow.add_node("planner", _planner_node)
    workflow.add_node("researcher", _researcher_node)
    workflow.add_node("reflector", _reflector_node)
    workflow.add_node("skills_extractor", _skills_extractor_node)
    
    # Define Edges
    workflow.set_entry_point("planner")
    workflow.add_edge("planner", "researcher")
    workflow.add_edge("researcher", "reflector")
    
    # Loop Protection & Conditional Exit
    def should_continue(state):
        if state["is_complete"] or state["iteration_count"] >= 10: # Recursion limit
            if state["iteration_count"] >= 10:
                logger.warning("Reached max iterations (10). Force terminating.")
            return "end"
        return "continue"
    
    workflow.add_conditional_edges(
        "reflector",
        should_continue,
        {
            "continue": "researcher",
            "end": "skills_extractor"
        }
    )
    workflow.add_edge("skills_extractor", END)
    
    # Initialize MemorySaver for Human-In-The-Loop and state persistence
    checkpointer = MemorySaver()
    
    return workflow.compile(checkpointer=checkpointer, interrupt_after=["planner"])
