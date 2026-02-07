import unittest
import os
from unittest.mock import patch
from deep_research_project.config.config import Configuration

class TestConfigSecurity(unittest.TestCase):
    def test_secrets_masked_in_str(self):
        """Test that secrets are masked in the string representation of Configuration."""
        with patch.dict(os.environ, {
            "OPENAI_API_KEY": "sk-secret-key",
            "OPENAI_API_BASE_URL": "https://user:password@api.openai.com/v1",
            "AZURE_OPENAI_API_KEY": "azure-secret-key",
            "AZURE_OPENAI_ENDPOINT": "https://user:pass@azure-endpoint.com",
            "OLLAMA_BASE_URL": "http://user:pass@localhost:11434",
            "TAVILY_API_KEY": "tv-secret-key",
            "LLM_PROVIDER": "openai",
            "SEARCH_API": "tavily"
        }):
            config = Configuration()
            config_str = str(config)

            # Check explicit keys are masked
            self.assertNotIn("sk-secret-key", config_str)
            self.assertIn("********", config_str)

            self.assertNotIn("azure-secret-key", config_str)

            # Check URLs are scrubbed
            # These assertions will fail before the fix
            self.assertNotIn("user:password", config_str)
            self.assertNotIn("user:pass", config_str)

            # Check TAVILY_API_KEY is not exposed (it is currently not printed at all, so this passes)
            self.assertNotIn("tv-secret-key", config_str)

if __name__ == '__main__':
    unittest.main()
