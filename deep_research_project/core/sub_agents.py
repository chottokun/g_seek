import logging
from typing import List, Dict, Any, Optional
from deep_research_project.tools.llm_client import LLMClient
from deep_research_project.config.config import Configuration

logger = logging.getLogger(__name__)

class SkillAgent:
    """A specialized sub-agent derived from a Skill (SKILL.md)."""
    
    def __init__(self, skill_id: str, skill_data: Dict, llm_client: LLMClient):
        self.skill_id = skill_id
        self.name = skill_data.get("name", skill_id)
        self.instructions = skill_data.get("content", "")
        self.description = skill_data.get("description", "")
        self.is_dynamic = skill_data.get("is_dynamic", False)
        self.llm_client = llm_client

    async def run_task(self, section_title: str, section_description: str, context: List[str], language: str) -> str:
        """Executes a specific research task using its specialized expertise."""
        logger.info(f"Sub-Agent '{self.name}' starting task: {section_title}")
        
        system_prompt = (
            f"You are a specialized research assistant expert in: {self.name}.\n"
            f"Description: {self.description}\n\n"
            "--- YOUR SPECIALIZED EXPERTISE ---\n"
            f"{self.instructions}\n\n"
            "--- MISSION ---\n"
            f"Research and summarize the following section: {section_title}\n"
            f"Goal: {section_description}\n"
            "Use the provided context to synthesize your findings."
        )
        
        user_prompt = (
            f"Current context/findings:\n" + "\n".join(context) + "\n\n"
            f"Please provide a detailed summary for '{section_title}' based on your expertise."
        )
        
        try:
            response = await self.llm_client.generate_text(user_prompt, system_prompt=system_prompt)
            return response
        except Exception as e:
            logger.error(f"Sub-Agent {self.name} failed: {e}")
            return f"Error in sub-agent {self.name}: {str(e)}"

class Orchestrator:
    """Manages routing and execution of SkillAgents."""
    
    def __init__(self, skills_mgr, llm_client: LLMClient):
        self.skills_mgr = skills_mgr
        self.llm_client = llm_client
        self.agents: Dict[str, SkillAgent] = {}

    def get_agent(self, skill_id: str) -> Optional[SkillAgent]:
        if skill_id not in self.agents:
            skill_data = self.skills_mgr.get_skill(skill_id)
            if skill_data:
                self.agents[skill_id] = SkillAgent(skill_id, skill_data, self.llm_client)
        return self.agents.get(skill_id)

    async def delegate_if_relevant(self, section_title: str, section_description: str, 
                                   activated_skill_ids: List[str], findings: List[str], 
                                   language: str) -> Optional[str]:
        """Delegates the task to the most relevant sub-agent among those activated."""
        if not activated_skill_ids:
            return None
            
        # Extract valid dynamic agents (domain skills) to act as specialized sub-agents
        valid_agents = []
        for sid in set(activated_skill_ids):
            agent = self.get_agent(sid)
            if agent and (agent.is_dynamic or sid.startswith("domain-")):
                valid_agents.append(agent)
                
        if not valid_agents:
            # If no specialized domain skill, fallback to normal search
            return None
            
        # Use the first valid specialized agent
        best_agent = valid_agents[0]
        logger.info(f"Orchestrator: Delegating '{section_title}' to Sub-Agent '{best_agent.name}'")
        return await best_agent.run_task(section_title, section_description, findings, language)
        
        return None
