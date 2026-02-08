import asyncio
import httpx
import pytest
from unittest.mock import patch, MagicMock

@pytest.mark.asyncio
async def test_ollama():
    url = "http://localhost:11434/api/tags"
    print(f"Testing Ollama connectivity (Mocked) at: {url}")
    
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {"models": [{"name": "mock-model"}]}
    
    with patch("httpx.AsyncClient.get", return_value=mock_response):
        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(url, timeout=5.0)
                if response.status_code == 200:
                    print("Successfully connected to Ollama (Mocked)!")
                    print("Models available:", response.json())
                else:
                    print(f"Failed to connect. Status code: {response.status_code}")
        except Exception as e:
            print(f"Connection error: {e}")

if __name__ == "__main__":
    asyncio.run(test_ollama())
