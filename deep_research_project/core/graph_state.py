from typing import List, Dict, Optional, TypedDict, Annotated, Any
import operator
from pydantic import BaseModel
from deep_research_project.core.state import SectionPlan, Source

class AgentState(TypedDict):
    """LangGraph State for Deep Research Agent."""
    topic: str
    language: str
    plan: List[SectionPlan]
    current_section_index: int
    # Use Annotated with operator.add to accumulate findings across nodes
    findings: Annotated[List[str], operator.add]
    sources: Annotated[List[Source], operator.add]
    knowledge_graph: Dict[str, List] # nodes and edges
    research_context: List[Dict] # From SkillsManager
    activated_skill_ids: List[str] # Tracking for refinement
    current_query: Optional[str] # For iterative research
    is_complete: bool
    iteration_count: int
    # For loop protection
    max_iterations: int
    newly_extracted_skill: Optional[str] # To inform the UI about new skills
    plan_approved: bool # For HITL flow tracking
    final_report: Optional[str]
    progress_callback: Optional[Any] # For real-time UI logging
