import logging
import asyncio
import re
import json
from pathlib import Path
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
            f"Current Topic: {state['topic']}\n\n"
            f"Available Past Research Skills:\n{skill_descriptions}\n\n"
            "Task: Select ONLY the skills that are strictly necessary and highly relevant to the current topic.\n"
            "Strict Guidelines:\n"
            "1. ONLY select 'domain-xxx' skills if the current topic is a direct follow-up or covers the exact same domain. If the topic is just broadly related, DO NOT select it.\n"
            "2. 'web-search' is a general tool and should be selected for most cases.\n"
            "3. If multiple skills seem similar, select only the most relevant one.\n"
            "4. Accuracy is more important than helpfulness. Do not pollute the context with irrelevant past data.\n\n"
            "Respond in JSON format:\n"
            "{\n"
            "  \"selected_ids\": [\"id1\", \"id2\"],\n"
            "  \"reasoning\": \"Brief explanation of why these specific skills are needed\"\n"
            "}"
        )
        try:
            # Using generate_text but parsing as JSON for reliability
            trigger_resp = await planner.llm_client.generate_text(trigger_prompt)
            # Find JSON block if any
            json_match = re.search(r"(\{.*\})", trigger_resp, re.DOTALL)
            if json_match:
                data = json.loads(json_match.group(1))
                selected_skill_ids = [sid for sid in data.get("selected_ids", []) if sid in skills_mgr.skills]
                logger.info(f"Skill Selection Reasoning: {data.get('reasoning')}")
            else:
                # Fallback to simple comma split if JSON parsing fails
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

from langchain_core.runnables import RunnableConfig

async def researcher_node(state: AgentState, config: RunnableConfig, planner: ResearchPlanner, executor: ResearchExecutor, orchestrator: Any):
    """Execution node. Performs web search or delegates to specialized sub-agents."""
    idx = state["current_section_index"]
    
    # Boundary check
    if idx < 0 or idx >= len(state["plan"]):
        return {"is_complete": True}
        
    section = state["plan"][idx]
    
    # Access configurable from RunnableConfig
    configurable = config.get("configurable", {})
    # Get the actual config object from configurable if it was passed that way, 
    # or use the one from the node argument (which might be the full config)
    # In LangGraph nodes, 'config' IS the RunnableConfig.
    app_config = configurable.get("config") # This is our Pydantic Configuration
    progress_cb = configurable.get("progress_callback")
    
    # Logic to decide next move...
    expert_guidance = await orchestrator.delegate_if_relevant(
        section_title=section["title"],
        section_description=section.get("description", ""),
        activated_skill_ids=state.get("activated_skill_ids", []),
        findings=state.get("findings", []),
        language=state["language"]
    )
    expert_context = f"\n\n--- EXPERT GUIDANCE ---\n{expert_guidance}" if expert_guidance else ""

    # If Not interactive and first section, we use ResearchLoop to finish all sections in parallel
    if not app_config.INTERACTIVE_MODE:
        from deep_research_project.core.research_loop import ResearchLoop
        from deep_research_project.core.state import ResearchState
        
        r_state = ResearchState(research_topic=state["topic"], language=state["language"])
        r_state.research_plan = state["plan"]
        r_state.current_section_index = idx
        
        loop = ResearchLoop(app_config, r_state, progress_callback=progress_cb)
        await loop.run_loop()
        
        all_findings = []
        all_sources = []
        for sec in r_state.research_plan:
            if sec.get('summary'): all_findings.append(sec['summary'])
            if sec.get('sources'): all_sources.extend(sec['sources'])
        
        return {
            "findings": all_findings,
            "sources": all_sources,
            "is_complete": True,
            "current_section_index": len(state["plan"])
        }

    # Sequential fallback
    query = await planner.generate_initial_query(
        topic=state["topic"],
        section_title=section["title"],
        section_description=section.get("description", "") + expert_context,
        language=state["language"],
        progress_callback=progress_cb
    )
    results = await executor.search(query, getattr(app_config, "MAX_SEARCH_RESULTS_PER_QUERY", 3))
    relevant = await executor.filter_by_relevance(query, results, state["language"], progress_callback=progress_cb)
    summary = await executor.retrieve_and_summarize(relevant, query, state["language"], progress_callback=progress_cb)
    
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
        
    from deep_research_project.core.prompts import (
        SKILLS_EXTRACTION_PROMPT_JA, SKILLS_EXTRACTION_PROMPT_EN,
        SKILLS_REFINEMENT_PROMPT_JA, SKILLS_REFINEMENT_PROMPT_EN
    )
    
    # Ensure findings exist
    if not state.get("findings"):
        logger.info("No findings available for skill extraction.")
        return {"newly_extracted_skill": None}
        
    findings_str = "\n\n".join(state["findings"])[:10000] # Increased context window
    is_japanese = state["language"] == "Japanese"

    from datetime import datetime
    current_date = datetime.now().strftime("%Y-%m-%d")
    
    import re
    # Create a stable ID based purely on the topic to allow evolution (no UUID)
    base_id = re.sub(r'[^a-zA-Z0-9-]', '-', state["topic"].lower())[:40].strip("-")
    # To avoid 'domain-' bare stems if topic is oddly filtered, provide fallback
    if not base_id:
        base_id = "general-research"
    skill_id = f"domain-{base_id}"
    
    existing_skill = skills_mgr.get_skill(skill_id)

    if existing_skill:
        logger.info(f"Refining existing domain skill: {skill_id}...")
        prompt_tpl = SKILLS_REFINEMENT_PROMPT_JA if is_japanese else SKILLS_REFINEMENT_PROMPT_EN
        prompt = prompt_tpl.format(
            topic=state["topic"],
            findings=findings_str, 
            current_date=current_date,
            current_skill=existing_skill.get("content", "")
        )
        action_log = "REFINED"
    else:
        logger.info(f"Extracting insights to create a new domain skill: {skill_id}...")
        prompt_tpl = SKILLS_EXTRACTION_PROMPT_JA if is_japanese else SKILLS_EXTRACTION_PROMPT_EN
        prompt = prompt_tpl.format(
            topic=state["topic"],
            findings=findings_str, 
            current_date=current_date
        )
        action_log = "CREATED NEW"
    
    try:
        extraction = await llm_client.generate_text(prompt)
        # Cleaner parsing of patterns
        patterns = []
        for line in extraction.strip().split("\n"):
            clean = line.strip("- ").strip("* ").strip()
            if clean and len(clean) > 5:
                patterns.append(clean)
        
        if patterns:
            skill_name = f"Domain: {state['topic'][:40]}"
            # Generate a better description using the extracted patterns
            summary_desc = ". ".join(patterns[:2])
            if len(summary_desc) > 150: summary_desc = summary_desc[:147] + "..."
            description = f"Methodology & Insights: {summary_desc}"
            
            content = "## Domain Expertise: " + state["topic"] + "\n\n"
            content += "### Key Methodological Patterns\n"
            content += "\n".join([f"- {p}" for p in patterns])
            
            # Save as a distinct new or refined skill
            await skills_mgr.save_skill(skill_id, skill_name, description, content, created_at=current_date)
            logger.info(f"SUCCESS: {action_log} domain skill: {skill_id}")
            return {"newly_extracted_skill": f"{skill_name} ({action_log})"}

    except Exception as e:
        logger.error(f"CRITICAL: Failed to extract/refine domain skill '{skill_id}': {e}")
            
    return {"newly_extracted_skill": None}

async def final_reporter_node(state: AgentState, reporter: ResearchReporter):
    """Generates the final research report."""
    logger.info(f"--- FINAL REPORTER NODE ---")
    
    findings = state.get("findings", [])
    sources = state.get("sources", [])
    
    logger.info(f"Synthesis input - Findings: {len(findings)} sections, Sources: {len(sources)} links")
    
    # Debug nested list structure if any
    if findings and isinstance(findings[0], list):
        logger.warning(f"Detected nested findings list! Flattening for reporter.")
        flattened_findings = []
        for f in findings:
            if isinstance(f, list): flattened_findings.extend(f)
            else: flattened_findings.append(f)
        findings = flattened_findings

    report = await reporter.finalize_report(
        topic=state["topic"],
        findings=findings,
        sources=sources,
        language=state["language"]
    )
    return {"final_report": report, "is_complete": True}

# --- Graph Construction ---

def create_research_graph(app_config: Configuration, llm_client: LLMClient, search_client: Any, content_retriever: Any):
    # Initialize components
    from deep_research_project.core.skills_manager import SkillRegistry
    from deep_research_project.core.sub_agents import Orchestrator
    planner = ResearchPlanner(app_config, llm_client)
    executor = ResearchExecutor(app_config, llm_client, search_client, content_retriever)
    reflector = ResearchReflector(app_config, llm_client)
    reporter = ResearchReporter(llm_client)
    
    # Ensure SkillRegistry uses a local directory within the project
    base_dir = Path(__file__).parent.parent
    skills_mgr = SkillRegistry(
        static_skills_dir=str(base_dir / "data" / "skills" / "static"),
        dynamic_skills_dir=str(base_dir / "data" / "skills" / "dynamic")
    )
    
    orchestrator = Orchestrator(skills_mgr, llm_client)
    
    workflow = StateGraph(AgentState)
    
    # Define Nodes with explicit signature that LangGraph can inspect reliably
    async def _planner_node(s, config: RunnableConfig): 
        return await planner_node(s, app_config, planner, skills_mgr)
    
    async def _researcher_node(s, config: RunnableConfig): 
        return await researcher_node(s, config, planner, executor, orchestrator)
    
    async def _reflector_node(s, config: RunnableConfig): 
        return await reflector_node(s, app_config, reflector)
    
    async def _skills_extractor_node(s, config: RunnableConfig): 
        return await skills_extractor_node(s, llm_client, skills_mgr, app_config)
    
    async def _final_reporter_node(s, config: RunnableConfig): 
        return await final_reporter_node(s, reporter)

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
    
    interrupts = ["planner"] if app_config.INTERACTIVE_MODE else []
    return workflow.compile(checkpointer=checkpointer, interrupt_after=interrupts)
