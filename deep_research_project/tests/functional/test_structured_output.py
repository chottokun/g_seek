import asyncio
import logging
from deep_research_project.config.config import Configuration
from deep_research_project.tools.llm_client import LLMClient
from deep_research_project.core.state import ResearchPlanModel

# Configure logging to see what's happening
logging.basicConfig(level=logging.INFO)

async def test_structured_output():
    config = Configuration()
    # Mock: use placeholder to avoid real LLM calls
    config.LLM_PROVIDER = "placeholder_llm"
    
    print(f"Testing structured output with Provider: {config.LLM_PROVIDER}")
    
    client = LLMClient(config)
    
    # Trigger placeholder logic in LLMClient
    prompt = "Generate a structured research plan for 'Quantum Computing'. Provide 3 sections."
    
    print("\nAttempting generate_structured (Mocked)...")
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
