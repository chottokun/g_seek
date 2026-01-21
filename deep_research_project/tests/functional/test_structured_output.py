import pytest
import asyncio
import logging
from deep_research_project.config.config import Configuration
from deep_research_project.tools.llm_client import LLMClient
from deep_research_project.core.state import ResearchPlanModel

# Configure logging to see what's happening
logging.basicConfig(level=logging.INFO)

@pytest.mark.anyio
async def test_structured_output():
    config = Configuration()
    # Ensure it's using the ollama provider as in .env
    print(f"Testing with Provider: {config.LLM_PROVIDER}, Model: {config.LLM_MODEL}")
    
    client = LLMClient(config)
    
    prompt = "Generate a research plan for 'Quantum Computing'. Provide 3 sections."
    
    print("\nAttempting generate_structured...")
    try:
        result = await client.generate_structured(prompt, ResearchPlanModel)
        print("\nSuccess!")
        print(result)
    except Exception as e:
        print(f"\nFailed! Error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(test_structured_output())
