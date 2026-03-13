import logging
import asyncio
from typing import List, Optional, Tuple, Callable
from deep_research_project.config.config import Configuration
from deep_research_project.tools.llm_client import LLMClient
from deep_research_project.core.state import KnowledgeGraphModel, Source, KGNode, KGEdge
from deep_research_project.core.prompts import (
    KG_EXTRACTION_PROMPT_JA, KG_EXTRACTION_PROMPT_EN,
    REFLECTION_PROMPT_JA, REFLECTION_PROMPT_EN
)
from deep_research_project.core.utils import sanitize_query


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

    def _merge_nodes(self, new_nodes: List[KGNode], existing_nodes: List[dict]):
        """Merges new nodes into the existing nodes list with O(N) complexity."""
        node_map = {n['id']: n for n in existing_nodes}
        for new_node in new_nodes:
            node_id = new_node.id
            if node_id in node_map:
                existing_node = node_map[node_id]
                
                # Merge properties
                if new_node.properties:
                    existing_node.setdefault('properties', {}).update(new_node.properties)
                
                # Update Centrality (mention_count)
                props = existing_node.setdefault('properties', {})
                try:
                    current_count = int(props.get('mention_count', '1'))
                    props['mention_count'] = str(current_count + 1)
                except (ValueError, TypeError):
                    props['mention_count'] = "2"

                # Merge source URLs (unique)
                new_urls = new_node.source_urls
                if new_urls:
                    existing_urls = existing_node.get('source_urls', [])
                    if not existing_urls:
                        existing_node['source_urls'] = list(new_urls)
                    else:
                        u_set = set(existing_urls)
                        u_set.update(new_urls)
                        existing_node['source_urls'] = list(u_set)
            else:
                node_data = new_node.model_dump()
                node_data.setdefault('properties', {})['mention_count'] = "1"
                existing_nodes.append(node_data)
                node_map[node_id] = node_data

    def _merge_edges(self, new_edges: List[KGEdge], existing_edges: List[dict]):
        """Merges new edges into the existing edges list."""
        edge_map = {(e['source'], e['target'], e.get('label')): e for e in existing_edges}
        for new_edge in new_edges:
            edge_key = (new_edge.source, new_edge.target, new_edge.label)
            if edge_key in edge_map:
                existing_edge = edge_map[edge_key]
                if new_edge.properties:
                    existing_edge.setdefault('properties', {}).update(new_edge.properties)
                
                if new_edge.source_urls:
                    existing_urls = existing_edge.get('source_urls', [])
                    if not existing_urls:
                        existing_edge['source_urls'] = list(new_edge.source_urls)
                    else:
                        u_set = set(existing_urls)
                        u_set.update(new_edge.source_urls)
                        existing_edge['source_urls'] = list(u_set)
            else:
                edge_data = new_edge.model_dump()
                existing_edges.append(edge_data)
                edge_map[edge_key] = edge_data

    def _merge_knowledge_graph(self, kg_model: KnowledgeGraphModel,
                                existing_nodes: List[dict], existing_edges: List[dict]):
        """Internal logic to merge newly extracted graph data into state using O(N) indexing."""
        self._merge_nodes(kg_model.nodes, existing_nodes)
        self._merge_edges(kg_model.edges, existing_edges)

    async def reflect_and_decide(self, topic: str, section_title: str, 
                                 section_description: str, accumulated_summary: str, 
                                 language: str) -> Tuple[str, Optional[str]]:
        """Evaluates if more research is needed for the current context."""
        from datetime import datetime
        current_date = datetime.now().strftime("%Y-%m-%d")

        if language == "Japanese":
            prompt = REFLECTION_PROMPT_JA.format(
                topic=topic,
                current_date=current_date,
                section_title=section_title,
                section_description=section_description,
                accumulated_summary=accumulated_summary
            )
        else:
            prompt = REFLECTION_PROMPT_EN.format(
                topic=topic,
                current_date=current_date,
                section_title=section_title,
                section_description=section_description,
                accumulated_summary=accumulated_summary
            )

        response = await self.llm_client.generate_text(prompt=prompt)
        lines = response.split('\n')
        evaluation = "CONCLUDE"
        next_query = None
        for line in lines:
            if "EVALUATION:" in line.upper(): 
                val = line.split(":", 1)[-1].strip().upper()
                if "CONTINUE" in val:
                    evaluation = "CONTINUE"
                else:
                    evaluation = "CONCLUDE"
            if "QUERY:" in line.upper():
                q = line.split(":", 1)[-1].strip()
                # Clean up potential markdown or quotes
                q = q.replace("`", "").replace("\"", "").strip()
                if q.lower() != "none" and len(q) > 2: 
                    # Sanitize the reflected query similarly to the initial query
                    next_query = sanitize_query(q)
        
        return evaluation, next_query

    async def reflect(self, topic: str, section_title: str, 
                      section_description: str, accumulated_summary: str, 
                      language: str) -> dict:
        """Alias for reflect_and_decide returning dict format for graph nodes."""
        evaluation, next_query = await self.reflect_and_decide(
            topic, section_title, section_description, accumulated_summary, language
        )
        return {"evaluation": evaluation, "query": next_query}
