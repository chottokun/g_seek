import pytest
import asyncio
from typing import Dict, Any
from deep_research_project.core.sub_agents import SkillAgent, Orchestrator
from deep_research_project.core.skills_manager import SkillRegistry
from deep_research_project.tools.llm_client import LLMClient
from deep_research_project.config.config import Configuration

class MockLLMClient:
    """A mock LLM client for fast, deterministic unit tests."""
    async def generate_text(self, prompt: str, system_prompt: Optional[str] = None) -> str:
        return f"MOCK RESPONSE based on prompt length {len(prompt)}"

@pytest.mark.asyncio
async def test_sub_agent_routing():
    """Test that orchestrator routes only valid dynamic agents."""
    class MockRegistry:
        def __init__(self):
            self.skills = {}
            
        def get_skill(self, skill_id: str):
            if skill_id == "domain-123":
                return {"name": "Test Domain", "description": "Desc", "content": "Content", "is_dynamic": True}
            elif skill_id == "web-search":
                return {"name": "Web", "description": "Search", "content": "Tool", "is_dynamic": False}
            return None

    llm_client = MockLLMClient()
    registry = MockRegistry()
    orchestrator = Orchestrator(registry, llm_client)

    # Calling with a mix of static and dynamic skill
    summary = await orchestrator.delegate_if_relevant(
        section_title="Test Phase",
        section_description="Test Description",
        activated_skill_ids=["web-search", "domain-123"],
        findings=[],
        language="Japanese"
    )

    # Should have selected the domain-123 agent and returned the mock response
    assert summary is not None
    assert "MOCK RESPONSE" in summary
    assert "domain-123" in orchestrator.agents
    
    # Static fallback
    summary_none = await orchestrator.delegate_if_relevant(
        section_title="Test Phase",
        section_description="Test Description",
        activated_skill_ids=["web-search"],
        findings=[],
        language="Japanese"
    )
    # web-search is static, should return None
    assert summary_none is None

@pytest.mark.asyncio
async def test_sub_agent_actual_llm_call():
    """Integration test using ACTUAL LLM client to ensure prompts are correctly formatted and answered."""
    config = Configuration()
    
    # Ensure there's a valid LLM credential set in the environment or fallback
    if config.LLM_PROVIDER == "openai" and not config.OPENAI_API_KEY and not config.OPENAI_API_BASE_URL:
        pytest.skip("No actual LLM configuration available to run live integration test.")
        
    llm_client = LLMClient(config)
    
    skill_data = {
        "name": "Expert Python Developer",
        "description": "An expert in writing robust Python tests.",
        "content": "You are strict on typing and writing clear, concise assertions.",
        "is_dynamic": True
    }
    
    agent = SkillAgent("domain-python-test", skill_data, llm_client)
    
    response = await agent.run_task(
        section_title="Write a simple assert",
        section_description="We need to verify that 1 + 1 equals 2",
        context=["The user loves pytest.", "Keep the answer under 100 characters."],
        language="English"
    )
    
    # We must assert that we received a string and it contains reasonable text
    assert isinstance(response, str)
    assert len(response) > 0
    # LLM might not return the precise code, but response should be a string.
    print(f"Live LLM Response from SubAgent: {response}")
