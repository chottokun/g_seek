import pytest
import asyncio
from deep_research_project.config.config import Configuration
from deep_research_project.tools.llm_client import LLMClient

@pytest.mark.anyio
async def test_simple_text():
    config = Configuration()
    client = LLMClient(config)
    print(f"Testing simple text generation with {config.LLM_MODEL}...")
    try:
        result = await client.generate_text("Say hello!")
        print(f"Response: {result}")
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    asyncio.run(test_simple_text())
