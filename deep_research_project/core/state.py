from typing import List, Dict, Optional, TypedDict
from pydantic import BaseModel, Field

class SearchResult(TypedDict):
    title: str
    link: str
    snippet: str # Or any other relevant fields from search API

class Source(TypedDict):
    title: str
    link: str

# Pydantic models for structured output
class Section(BaseModel):
    title: str = Field(description="Title of the research section")
    description: str = Field(description="Detailed description of what to research in this section")

class ResearchPlanModel(BaseModel):
    sections: List[Section] = Field(description="List of research sections")

class KGNode(BaseModel):
    id: str = Field(description="Unique identifier for the node")
    label: str = Field(description="Label or name of the entity")
    type: str = Field(description="Type of the entity (e.g., Person, Organization, Concept)")

class KGEdge(BaseModel):
    source: str = Field(description="ID of the source node")
    target: str = Field(description="ID of the target node")
    label: str = Field(description="Label describing the relationship")

class KnowledgeGraphModel(BaseModel):
    nodes: List[KGNode]
    edges: List[KGEdge]

class SectionPlan(TypedDict):
    title: str
    description: str
    status: str # "pending", "researching", "completed"
    summary: str
    sources: List[Source]

class ResearchState:
    def __init__(self, research_topic: str):
        self.research_topic: str = research_topic
        self.initial_query: Optional[str] = None
        self.proposed_query: Optional[str] = None
        self.current_query: Optional[str] = None
        self.search_results: Optional[List[SearchResult]] = None
        self.new_information: Optional[str] = None # Summary of the latest search results
        self.sources_gathered: List[Source] = []
        self.accumulated_summary: str = "" # Initialize as empty string
        self.completed_loops: int = 0
        self.final_report: Optional[str] = None
        self.pending_source_selection: bool = False
        self.fetched_content: Optional[Dict[str, str]] = None
        self.knowledge_graph_nodes: List[Dict] = []
        self.knowledge_graph_edges: List[Dict] = []
        self.follow_up_log: List[Dict[str, str]] = []

        # New fields for multi-section research
        self.research_plan: List[SectionPlan] = []
        self.current_section_index: int = -1 # -1 means plan not yet generated
        self.plan_approved: bool = False

    def __str__(self):
        plan_status = f"{len(self.research_plan)} sections" if self.research_plan else "Not generated"
        current_sec = f"{self.current_section_index + 1}/{len(self.research_plan)}" if self.research_plan else "N/A"

        return (
            f"ResearchState:\n"
            f"  Topic: {self.research_topic}\n"
            f"  Plan: {plan_status} (Approved: {self.plan_approved})\n"
            f"  Current Section: {current_sec}\n"
            f"  Initial Query: {self.initial_query}\n"
            f"  Proposed Query: {self.proposed_query}\n"
            f"  Current Query: {self.current_query}\n"
            f"  Search Results Count: {len(self.search_results) if self.search_results else 0}\n"
            f"  New Information: {'Yes' if self.new_information else 'No'}\n"
            f"  Sources Gathered Count: {len(self.sources_gathered)}\n"
            f"  Accumulated Summary Length: {len(self.accumulated_summary)}\n"
            f"  Completed Loops: {self.completed_loops}\n"
            f"  Pending Source Selection: {self.pending_source_selection}\n"
            f"  Fetched Content Count: {len(self.fetched_content) if self.fetched_content else 0}\n"
            f"  Knowledge Graph Nodes: {len(self.knowledge_graph_nodes)}\n"
            f"  Knowledge Graph Edges: {len(self.knowledge_graph_edges)}\n"
            f"  Follow-up Q&A Count: {len(self.follow_up_log)}\n"
            f"  Final Report: {'Generated' if self.final_report else 'Not yet generated'}"
        )
