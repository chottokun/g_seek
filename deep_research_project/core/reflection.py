import logging
import asyncio
from typing import List, Optional, Tuple, Callable
from deep_research_project.config.config import Configuration
from deep_research_project.tools.llm_client import LLMClient
from deep_research_project.core.state import KnowledgeGraphModel, Source
from deep_research_project.core.prompts import KG_EXTRACTION_PROMPT_JA, KG_EXTRACTION_PROMPT_EN

logger = logging.getLogger(__name__)

class ResearchReflector:
    def __init__(self, config: Configuration, llm_client: LLMClient):
        self.config = config
        self.llm_client = llm_client

    async def extract_knowledge_graph(self, text: str, sources: List[Source], 
                                    section_title: str, language: str, 
                                    existing_nodes: List[dict], existing_edges: List[dict]):
        """Extracts entities and relations from text and merges them into the existing graph."""
        if not text or len(text) < 20: return

        active_urls = [s.link for s in sources]
        urls_str = "\n".join([f"- {url}" for url in active_urls])

        if language == "Japanese":
            prompt = KG_EXTRACTION_PROMPT_JA.format(
                text=text, urls=urls_str, section_title=section_title
            )
        else:
            prompt = KG_EXTRACTION_PROMPT_EN.format(
                text=text, urls=urls_str, section_title=section_title
            )

        try:
            kg_model = await self.llm_client.generate_structured(prompt=prompt, response_model=KnowledgeGraphModel)
            self._merge_knowledge_graph(kg_model, existing_nodes, existing_edges)
        except Exception as e:
            logger.error(f"KG extraction or merge failed: {e}")

    def _merge_knowledge_graph(self, kg_model: KnowledgeGraphModel, 
                               existing_nodes: List[dict], existing_edges: List[dict]):
        """Internal logic to merge newly extracted graph data into state."""
        # Merge Nodes
        for new_node in kg_model.nodes:
            existing_node = next((n for n in existing_nodes if n['id'] == new_node.id), None)
            if existing_node:
                existing_node.setdefault('properties', {}).update(new_node.properties)
                existing_urls = set(existing_node.get('source_urls', []))
                existing_urls.update(new_node.source_urls)
                existing_node['source_urls'] = list(existing_urls)
                # Centarity
                props = existing_node['properties']
                props['mention_count'] = str(int(props.get('mention_count', 1)) + 1)
            else:
                node_data = new_node.model_dump()
                node_data['properties']['mention_count'] = "1"
                existing_nodes.append(node_data)

        # Merge Edges
        for new_edge in kg_model.edges:
            edge_key = (new_edge.source, new_edge.target, new_edge.label)
            existing_edge = next((e for e in existing_edges if (e['source'], e['target'], e.get('label')) == edge_key), None)
            if existing_edge:
                existing_edge.setdefault('properties', {}).update(new_edge.properties)
                existing_urls = set(existing_edge.get('source_urls', []))
                existing_urls.update(new_edge.source_urls)
                existing_edge['source_urls'] = list(existing_urls)
            else:
                existing_edges.append(new_edge.model_dump())

    async def reflect_and_decide(self, topic: str, section_title: str, 
                                 accumulated_summary: str, language: str) -> Tuple[str, Optional[str]]:
        """Evaluates if more research is needed for the current context."""
        if language == "Japanese":
            prompt = (
                f"トピック: {topic}\n"
                f"セクション: {section_title}\n"
                f"現在の要約:\n{accumulated_summary}\n\n"
                f"このセクションにさらなる調査が必要かどうかを評価してください。"
                f"フォーマット: EVALUATION: <CONTINUE|CONCLUDE>\nQUERY: <次の検索クエリまたは None>"
            )
        else:
            prompt = (
                f"Topic: {topic}\n"
                f"Section: {section_title}\n"
                f"Current Summary:\n{accumulated_summary}\n\n"
                f"Evaluate if more research is needed for this section. "
                f"Format: EVALUATION: <CONTINUE|CONCLUDE>\nQUERY: <Next search query or None>"
            )

        response = await self.llm_client.generate_text(prompt=prompt)
        lines = response.split('\n')
        evaluation = "CONCLUDE"
        next_query = None
        for line in lines:
            if "EVALUATION:" in line.upper(): evaluation = line.split(":")[-1].strip().upper()
            if "QUERY:" in line.upper():
                q = line.split(":")[-1].strip()
                if q.lower() != "none": next_query = q
        
        return evaluation, next_query
