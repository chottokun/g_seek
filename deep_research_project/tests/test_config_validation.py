import unittest
import os
from unittest.mock import patch
from pydantic import ValidationError
from deep_research_project.config.config import Configuration

class TestConfigValidation(unittest.TestCase):
    def test_invalid_temperature_type(self):
        # LLM_TEMPERATURE must be a float. Test string input.
        with patch.dict(os.environ, {"LLM_TEMPERATURE": "not-a-float"}):
            with self.assertRaises(ValidationError):
                Configuration()

    def test_invalid_max_tokens_type(self):
        with patch.dict(os.environ, {"LLM_MAX_TOKENS": "invalid"}):
            with self.assertRaises(ValidationError):
                Configuration()

    def test_custom_validator_overlap_size(self):
        # We implemented a validator: overlap must be < size
        with patch.dict(os.environ, {
            "SUMMARIZATION_CHUNK_SIZE_CHARS": "100",
            "SUMMARIZATION_CHUNK_OVERLAP_CHARS": "150"
        }):
            with self.assertRaises(ValueError) as context:
                Configuration()
            self.assertIn("SUMMARIZATION_CHUNK_OVERLAP_CHARS must be less than", str(context.exception))

    def test_log_level_normalization(self):
        with patch.dict(os.environ, {"LOG_LEVEL": "debug"}):
            config = Configuration()
            self.assertEqual(config.LOG_LEVEL, "DEBUG")

    def test_default_values(self):
        # Clear specific env vars to test defaults
        with patch.dict(os.environ, {}, clear=True):
            config = Configuration()
            self.assertEqual(config.LLM_PROVIDER, "placeholder_llm")
            self.assertEqual(config.INTERACTIVE_MODE, False)

    def test_available_providers(self):
        # Case 1: Only placeholder (default)
        with patch.dict(os.environ, {}, clear=True):
            config = Configuration()
            self.assertEqual(config.get_available_providers(), ["placeholder_llm"])

        # Case 2: OpenAI and Gemini configured
        with patch.dict(os.environ, {
            "OPENAI_API_KEY": "sk-test",
            "GOOGLE_API_KEY": "AIza-test"
        }, clear=True):
            config = Configuration()
            providers = config.get_available_providers()
            self.assertIn("openai", providers)
            self.assertIn("gemini", providers)
            self.assertIn("placeholder_llm", providers)
            self.assertNotIn("azure_openai", providers)
            self.assertNotIn("ollama", providers)

        # Case 3: Ollama configured
        with patch.dict(os.environ, {
            "OLLAMA_BASE_URL": "http://localhost:11434"
        }, clear=True):
            config = Configuration()
            providers = config.get_available_providers()
            self.assertIn("ollama", providers)
            self.assertIn("placeholder_llm", providers)

if __name__ == "__main__":
    unittest.main()
