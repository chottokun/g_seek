import asyncio
from typing import Any
from unittest.mock import MagicMock

# Mocking the Configuration and other dependencies to test LLMClient's internal logic
class MockConfig:
    LLM_PROVIDER = "gemini"
    LLM_MODEL = "gemini-2.0-flash-exp"
    LLM_TEMPERATURE = 0.7
    LLM_MAX_TOKENS = 1000
    GOOGLE_API_KEY = "fake_key"
    ENABLE_CACHING = False
    LLM_RATE_LIMIT_RPM = 60

# We'll test the logic by mocking the ainvoke method
async def test_llm_conversion():
    from deep_research_project.tools.llm_client import LLMClient
    
    client = LLMClient(MockConfig())
    
    # Mock the underlying LangChain LLM
    mock_llm = MagicMock()
    
    # Simulate a response that contains a list in its content (similar to what Gemini did)
    mock_response = MagicMock()
    mock_response.content = ["First line.", "Second line."]
    
    # Replace the actual invoke call with our mock
    # We need to mock ainvoke which is what generate_text uses
    future = asyncio.Future()
    future.set_result(mock_response)
    mock_llm.ainvoke.return_value = future
    
    client.llm = mock_llm
    
    print("Testing list-to-string conversion in LLMClient...")
    result = await client.generate_text("test prompt")
    
    print(f"Result type: {type(result)}")
    print(f"Result content:\n{result}")
    
    if isinstance(result, str) and "First line.\nSecond line." in result:
        print("\nSUCCESS: List was correctly converted to a newline-joined string.")
    else:
        print("\nFAILURE: Conversion failed.")

if __name__ == "__main__":
    # We need to mock some imports because ChatGoogleGenerativeAI might not be available in this environment
    import sys
    sys.modules['langchain_google_genai'] = MagicMock()
    
    asyncio.run(test_llm_conversion())
