import asyncio
from deep_research_project.config.config import Configuration
from deep_research_project.tools.llm_client import LLMClient
from deep_research_project.core.graph import create_research_graph

config = Configuration()
llm = LLMClient(config)
try:
    graph = create_research_graph(config, llm, None, None)
    print("Graph created successfully!")
except Exception as e:
    import traceback
    traceback.print_exc()
