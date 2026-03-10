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
            "Analyze the topic and the list of available skills. "
            "Select ONLY the skills that are directly relevant and strictly necessary for researching this specific topic. "
            "Guidelines:\n"
            "1. 'web-search' and 'arxiv-research' are general utility skills and should be selected if the topic is technical or news-oriented.\n"
            "2. 'domain-xxx' skills contain specific past research findings. ONLY select them if the current topic is a direct continuation or deeply related to that specific domain.\n"
            "3. If in doubt, do not select a skill.\n\n"
            "Respond with a comma-separated list of skill IDs, or 'None' if no skills are strictly relevant."
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
        "current_query": None,
        "plan_approved": False,
        "findings": [],
        "sources": []
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
    print(f"DEBUG: Researcher Node Hit for section index {idx}, title: {section['title']}")
    
    # Sub-agent Guidance Attempt
    # Use sub-agent expertise to enrich the research process
    expert_guidance = await orchestrator.delegate_if_relevant(
        section_title=section["title"],
        section_description=section.get("description", ""),
        activated_skill_ids=state.get("activated_skill_ids", []),
        findings=state.get("findings", []),
        language=state["language"]
    )
    
    expert_context = f"\n\n--- EXPERT GUIDANCE ---\n{expert_guidance}" if expert_guidance else ""
        
    # Standard Web Search Workflow
    # Generate Query (only if no current_query provided by Reflector)
    query = state.get("current_query")
    if not query:
        print("DEBUG: Generating initial query...")
        query = await planner.generate_initial_query(
            topic=state["topic"],
            section_title=section["title"],
            section_description=section.get("description", "") + expert_context,
            language=state["language"]
        )
    print(f"DEBUG: Search Query: {query}")
    
    # Search
    print(f"DEBUG: Executing search for: {query}")
    results = await executor.search(query, getattr(config, "MAX_SEARCH_RESULTS_PER_QUERY", 3))
    print(f"DEBUG: Found {len(results)} raw search results")
    
    # Filter
    relevant = await executor.filter_by_relevance(query, results, state["language"])
    print(f"DEBUG: Found {len(relevant)} relevant search results")
    
    # Retrieve & Summarize with TRUNCATION for logs
    summary = await executor.retrieve_and_summarize(relevant, query, state["language"])
    print(f"DEBUG: Summary generated, length: {len(summary)}")
    
    # Truncate for logging purposes if needed, but findings should stay intact
    safe_summary_log = (summary[:500] + '...') if len(summary) > 500 else summary
    logger.debug(f"Gathered summary (truncated for log): {safe_summary_log}")
    
    return {
        "findings": [summary],
        "sources": [{"title": r.title, "link": r.link} for r in relevant],
        "current_query": query,
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
            "iteration_count": 0,  # Reset loop counter for the new section
            "is_complete": is_complete
        }

async def skills_extractor_node(state: AgentState, llm_client: LLMClient, skills_mgr: SkillRegistry, config: Configuration):
    """Learns research expertise and generates or refines standardized SKILL.md documents."""
    logger.info(f"--- SKILLS EXTRACTOR NODE ---")
    
    if not getattr(config, "EVOLVE_SKILLS", True):
        logger.info("EVOLVE_SKILLS is disabled. Skipping skill extraction.")
        return {"newly_extracted_skill": None}
        
    from deep_research_project.core.prompts import SKILLS_EXTRACTION_PROMPT_JA, SKILLS_EXTRACTION_PROMPT_EN
    
    # Ensure findings exist
    if not state.get("findings"):
        logger.info("No findings available for skill extraction.")
        return {"newly_extracted_skill": None}
        
    findings_str = "\n\n".join(state["findings"])[:10000] # Increased context window
    is_japanese = state["language"] == "Japanese"

    from datetime import datetime
    current_date = datetime.now().strftime("%Y-%m-%d")

    logger.info("Extracting insights to create a new dedicated domain skill...")
    prompt_tpl = SKILLS_EXTRACTION_PROMPT_JA if is_japanese else SKILLS_EXTRACTION_PROMPT_EN
    prompt = prompt_tpl.format(findings=findings_str, current_date=current_date)
    
    try:
        extraction = await llm_client.generate_text(prompt)
        # Cleaner parsing of patterns
        patterns = []
        for line in extraction.strip().split("\n"):
            clean = line.strip("- ").strip("* ").strip()
            if clean and len(clean) > 5:
                patterns.append(clean)
        
        if patterns:
            import re
            import uuid
            # Ensure unique ID for the specific topic domain
            base_id = re.sub(r'[^a-zA-Z0-9-]', '-', state["topic"].lower())[:30].strip("-")
            skill_id = f"domain-{base_id}-{uuid.uuid4().hex[:6]}"
            skill_name = f"Domain: {state['topic'][:40]}..."
            description = f"Specialized methodology and insights for: {state['topic']}."
            
            content = "## Domain Expertise: " + state["topic"] + "\n\n"
            content += "### Key Methodological Patterns\n"
            content += "\n".join([f"- {p}" for p in patterns])
            
            # Save as a distinct new skill
            skills_mgr.save_skill(skill_id, skill_name, description, content, created_at=current_date)
            logger.info(f"SUCCESS: Created NEW domain skill: {skill_id}")
            return {"newly_extracted_skill": skill_name}

    except Exception as e:
        logger.error(f"CRITICAL: Failed to extract domain skill: {e}")
            
    return {"newly_extracted_skill": None}

async def final_reporter_node(state: AgentState, reporter: ResearchReporter):
    """Generates the final research report."""
    logger.info(f"--- FINAL REPORTER NODE ---")
    report = await reporter.finalize_report(
        topic=state["topic"],
        findings=state["findings"],
        sources=state["sources"],
        language=state["language"]
    )
    return {"final_report": report, "is_complete": True}

# --- Graph Construction ---

def create_research_graph(config: Configuration, llm_client: LLMClient, search_client: Any, content_retriever: Any):
    # Initialize components
    from deep_research_project.core.skills_manager import SkillRegistry
    from deep_research_project.core.sub_agents import Orchestrator
    planner = ResearchPlanner(config, llm_client)
    executor = ResearchExecutor(config, llm_client, search_client, content_retriever)
    reflector = ResearchReflector(config, llm_client)
    reporter = ResearchReporter(llm_client)
    skills_mgr = SkillRegistry()
    orchestrator = Orchestrator(skills_mgr, llm_client)
    
    workflow = StateGraph(AgentState)
    
    # Define Nodes with partial application for dependencies
    async def _planner_node(s): return await planner_node(s, config, planner, skills_mgr)
    async def _researcher_node(s): return await researcher_node(s, config, planner, executor, orchestrator)
    async def _reflector_node(s): return await reflector_node(s, config, reflector)
    async def _skills_extractor_node(s): return await skills_extractor_node(s, llm_client, skills_mgr, config)
    async def _final_reporter_node(s): return await final_reporter_node(s, reporter)

    workflow.add_node("planner", _planner_node)
    workflow.add_node("researcher", _researcher_node)
    workflow.add_node("reflector", _reflector_node)
    workflow.add_node("skills_extractor", _skills_extractor_node)
    workflow.add_node("final_reporter", _final_reporter_node)
    
    # Define Edges
    workflow.set_entry_point("planner")
    workflow.add_edge("planner", "researcher")
    workflow.add_edge("researcher", "reflector")
    
    # Loop Protection & Conditional Exit
    def should_continue(state: AgentState):
        if state.get("is_complete") or state.get("iteration_count", 0) >= state.get("max_iterations", 10):
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
    workflow.add_edge("skills_extractor", "final_reporter")
    workflow.add_edge("final_reporter", END)
    
    # Initialize MemorySaver for Human-In-The-Loop and state persistence
    checkpointer = MemorySaver()
    
    interrupts = ["planner"] if config.INTERACTIVE_MODE else []
    return workflow.compile(checkpointer=checkpointer, interrupt_after=interrupts)
