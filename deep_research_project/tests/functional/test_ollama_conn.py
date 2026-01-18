import asyncio
import httpx
import sys
import os

async def test_ollama():
    url = "http://localhost:11434/api/tags"
    print(f"Connecting to Ollama at: {url}")
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(url, timeout=5.0)
            if response.status_code == 200:
                print("Successfully connected to Ollama!")
                print("Models available:", response.json())
            else:
                print(f"Failed to connect. Status code: {response.status_code}")
    except Exception as e:
        print(f"Connection error: {e}")

if __name__ == "__main__":
    asyncio.run(test_ollama())
