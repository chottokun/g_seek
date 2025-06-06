from typing import List, Dict, Optional, TypedDict

class SearchResult(TypedDict):
    title: str
    link: str
    snippet: str # Or any other relevant fields from search API

class Source(TypedDict):
    title: str
    link: str

class ResearchState:
    def __init__(self, research_topic: str):
        self.research_topic: str = research_topic
        self.initial_query: Optional[str] = None
        self.proposed_query: Optional[str] = None # Added this line
        self.current_query: Optional[str] = None
        self.search_results: Optional[List[SearchResult]] = None
        self.new_information: Optional[str] = None # Summary of the latest search results
        self.sources_gathered: List[Source] = []
        self.accumulated_summary: str = "" # Initialize as empty string
        self.completed_loops: int = 0
        self.final_report: Optional[str] = None
        self.pending_source_selection: bool = False # Added this line
        self.fetched_content: Optional[Dict[str, str]] = None # Added this line
        self.knowledge_graph_nodes: List[Dict] = []
        self.knowledge_graph_edges: List[Dict] = []

    def __str__(self):
        return (
            f"ResearchState:\n"
            f"  Topic: {self.research_topic}\n"
            f"  Initial Query: {self.initial_query}\n"
            f"  Proposed Query: {self.proposed_query}\n" # Added this line
            f"  Current Query: {self.current_query}\n"
            f"  Search Results Count: {len(self.search_results) if self.search_results else 0}\n"
            f"  New Information: {'Yes' if self.new_information else 'No'}\n"
            f"  Sources Gathered Count: {len(self.sources_gathered)}\n"
            f"  Accumulated Summary Length: {len(self.accumulated_summary)}\n"
            f"  Completed Loops: {self.completed_loops}\n"
            f"  Pending Source Selection: {self.pending_source_selection}\n" # Added this line
            f"  Fetched Content Count: {len(self.fetched_content) if self.fetched_content else 0}\n" # Added this line
            f"  Knowledge Graph Nodes: {len(self.knowledge_graph_nodes)}\n"
            f"  Knowledge Graph Edges: {len(self.knowledge_graph_edges)}\n"
            f"  Final Report: {'Generated' if self.final_report else 'Not yet generated'}"
        )

# Example usage (optional, for testing)
if __name__ == "__main__":
    state = ResearchState(research_topic="The impact of AI on climate change")
    print(state)

    state.initial_query = "AI impact on climate change"
    state.current_query = "AI solutions for carbon emission reduction"
    state.search_results = [
        SearchResult(title="AI can help with climate change", link="http://example.com/ai-climate", snippet="AI offers new ways...")
    ]
    state.new_information = "AI can be used to optimize energy grids."
    state.sources_gathered.append(Source(title="AI can help with climate change", link="http://example.com/ai-climate"))
    state.accumulated_summary = "Initial findings suggest AI has a role. AI can be used to optimize energy grids."
    state.completed_loops = 1
    print("\nUpdated State:")
    print(state)
