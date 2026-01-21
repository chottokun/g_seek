import unittest
from unittest.mock import patch, MagicMock, AsyncMock
from pydantic import BaseModel
from deep_research_project.config.config import Configuration
from deep_research_project.tools.llm_client import LLMClient

class MockResponseModel(BaseModel):
    summary: str
    key_points: list[str]

class TestLLMClientExtended(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.mock_config = MagicMock(spec=Configuration)
        self.mock_config.LLM_PROVIDER = "openai"
        self.mock_config.LLM_MODEL = "gpt-4o"
        self.mock_config.LLM_TEMPERATURE = 0.5
        self.mock_config.LLM_MAX_TOKENS = 500
        self.mock_config.OPENAI_API_KEY = "sk-test"
        self.mock_config.OPENAI_API_BASE_URL = None
        self.mock_config.LLM_MAX_RPM = 60
        self.mock_config.LLM_MAX_PARALLEL_REQUESTS = 5

    @patch('langchain_openai.AzureChatOpenAI')
    async def test_azure_initialization(self, mock_azure):
        self.mock_config.LLM_PROVIDER = "azure_openai"
        self.mock_config.AZURE_OPENAI_ENDPOINT = "https://test.openai.azure.com/"
        self.mock_config.AZURE_OPENAI_API_KEY = "key"
        self.mock_config.AZURE_OPENAI_API_VERSION = "2023-05-15"
        self.mock_config.AZURE_OPENAI_DEPLOYMENT_NAME = "gpt-35"
        
        client = LLMClient(self.mock_config)
        self.assertIsNotNone(client.llm)
        mock_azure.assert_called_once()

    @patch('langchain_ollama.ChatOllama')
    async def test_ollama_initialization(self, mock_ollama):
        self.mock_config.LLM_PROVIDER = "ollama"
        self.mock_config.LLM_MODEL = "llama3"
        self.mock_config.OLLAMA_BASE_URL = "http://localhost:11434"
        
        client = LLMClient(self.mock_config)
        self.assertIsNotNone(client.llm)
        mock_ollama.assert_called_once()

    @patch('langchain_openai.ChatOpenAI')
    async def test_structured_fallback(self, mock_chat):
        # Setup client
        client = LLMClient(self.mock_config)
        client.llm = MagicMock()
        
        # Mock with_structured_output to fail
        client.llm.with_structured_output.side_effect = Exception("Not supported")
        
        # Mock generate_text to return valid JSON for the parser
        mock_json = '{"summary": "test summary", "key_points": ["p1", "p2"]}'
        with patch.object(client, 'generate_text', new_callable=AsyncMock) as mock_gen_text:
            mock_gen_text.return_value = mock_json
            
            res = await client.generate_structured("test prompt", MockResponseModel)
            
            self.assertIsInstance(res, MockResponseModel)
            self.assertEqual(res.summary, "test summary")
            self.assertEqual(len(res.key_points), 2)
            mock_gen_text.assert_called_once()

    @patch('langchain_openai.ChatOpenAI')
    async def test_error_handling_ainvoke(self, mock_chat):
        client = LLMClient(self.mock_config)
        client.llm = MagicMock()
        client.llm.ainvoke = AsyncMock(side_effect=IOError("Connection failed"))
        
        with self.assertRaises(IOError):
            await client.generate_text("test")

if __name__ == '__main__':
    unittest.main()
