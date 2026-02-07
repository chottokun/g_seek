import asyncio
from deep_research_project.config.config import Configuration
from deep_research_project.tools.llm_client import LLMClient

async def test_simple_text():
    config = Configuration()
    # Mock: use placeholder to avoid real LLM calls
    config.LLM_PROVIDER = "placeholder_llm"
    
    client = LLMClient(config)
    print(f"Testing simple text generation with {config.LLM_PROVIDER} (Mocked)...")
    try:
        result = await client.generate_text("Say hello!")
        print(f"Response: {result}")
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    asyncio.run(test_simple_text())
