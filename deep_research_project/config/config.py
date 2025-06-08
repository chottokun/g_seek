import os
from dotenv import load_dotenv
from typing import Optional # Added for type hinting

# Load environment variables from .env file
load_dotenv()

class Configuration:
    def __init__(self):
        # LLM Configuration
        # LLM_PROVIDER: Specifies the LLM provider to use (e.g., "openai", "ollama", "azure_openai", "placeholder_llm").
        self.LLM_PROVIDER = os.getenv("LLM_PROVIDER", "placeholder_llm")
        # LLM_MODEL: Specifies the model name for the selected provider.
        # For Azure OpenAI, this should be your DEPLOYMENT NAME.
        self.LLM_MODEL = os.getenv("LLM_MODEL", "default_model_name")
        # LLM_TEMPERATURE: Controls randomness. Lower is more deterministic.
        self.LLM_TEMPERATURE: float = float(os.getenv("LLM_TEMPERATURE", 0.7))
        # LLM_MAX_TOKENS: Maximum number of tokens to generate.
        self.LLM_MAX_TOKENS: int = int(os.getenv("LLM_MAX_TOKENS", 1024)) # Default was 256, increased to 1024

        # OpenAI Specific Configuration (also used for LiteLLM proxies)
        self.OPENAI_API_KEY: Optional[str] = os.getenv("OPENAI_API_KEY")
        # OPENAI_API_BASE_URL: Optional. Use for OpenAI-compatible APIs (e.g., LiteLLM, local LLMs). If None, uses default OpenAI.
        self.OPENAI_API_BASE_URL: Optional[str] = os.getenv("OPENAI_API_BASE_URL", None)

        # Azure OpenAI Specific Configuration: Required settings for using Azure OpenAI directly.
        self.AZURE_OPENAI_API_KEY: Optional[str] = os.getenv("AZURE_OPENAI_API_KEY", None)
        self.AZURE_OPENAI_ENDPOINT: Optional[str] = os.getenv("AZURE_OPENAI_ENDPOINT", None)
        # AZURE_OPENAI_API_VERSION: API version, e.g., "2023-12-01-preview".
        self.AZURE_OPENAI_API_VERSION: Optional[str] = os.getenv("AZURE_OPENAI_API_VERSION", None)
        # AZURE_OPENAI_DEPLOYMENT_NAME: Your Azure deployment name (used as LLM_MODEL if provider is "azure_openai").
        self.AZURE_OPENAI_DEPLOYMENT_NAME: Optional[str] = os.getenv("AZURE_OPENAI_DEPLOYMENT_NAME", None)

        # Ollama Specific Configuration
        self.OLLAMA_BASE_URL: Optional[str] = os.getenv("OLLAMA_BASE_URL", None)
        # Number of retries for Ollama connection errors, 0 means one attempt only.
        self.OLLAMA_NUM_RETRIES: int = int(os.getenv("OLLAMA_NUM_RETRIES", 1))
        # Delay in seconds between retries for Ollama.
        self.OLLAMA_RETRY_DELAY_SECONDS: float = float(os.getenv("OLLAMA_RETRY_DELAY_SECONDS", 2.0))


        # Search Configuration
        self.SEARCH_API: str = os.getenv("SEARCH_API", "duckduckgo")
        self.TAVILY_API_KEY = os.getenv("TAVILY_API_KEY")
        self.SEARXNG_BASE_URL = os.getenv("SEARXNG_BASE_URL", "http://localhost:8080")

        # Research Loop Configuration
        self.MAX_RESEARCH_LOOPS = int(os.getenv("MAX_RESEARCH_LOOPS", "3"))
        self.MAX_SEARCH_RESULTS_PER_QUERY = int(os.getenv("MAX_SEARCH_RESULTS_PER_QUERY", "3"))

        # Output Configuration
        self.OUTPUT_FILENAME = os.getenv("OUTPUT_FILENAME", "research_report.md")

        # Logging Configuration
        self.LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()

        # Interactive Mode Configuration
        self.INTERACTIVE_MODE = os.getenv("INTERACTIVE_MODE", "True").lower() == "true"

        # Summarization Configuration
        self.SUMMARIZATION_CHUNK_SIZE_CHARS: int = int(os.getenv("SUMMARIZATION_CHUNK_SIZE_CHARS", 10000))
        self.SUMMARIZATION_CHUNK_OVERLAP_CHARS: int = int(os.getenv("SUMMARIZATION_CHUNK_OVERLAP_CHARS", 500))
        self.USE_SNIPPETS_ONLY_MODE: bool = os.getenv("USE_SNIPPETS_ONLY_MODE", "False").lower() == 'true'
        self.MAX_TEXT_LENGTH_PER_SOURCE_CHARS: int = int(os.getenv("MAX_TEXT_LENGTH_PER_SOURCE_CHARS", 0))
        self.PROCESS_PDF_FILES: bool = os.getenv("PROCESS_PDF_FILES", "True").lower() == 'true'


        # Perform any validation or conditional setup if needed
        if self.LLM_PROVIDER == "openai" and not self.OPENAI_API_KEY and not self.OPENAI_API_BASE_URL:
            # If using default OpenAI provider and no custom base URL, API key is essential.
            # If OPENAI_API_BASE_URL is set, it might be a proxy or local LLM not requiring a key.
            raise ValueError("OPENAI_API_KEY is required when LLM_PROVIDER is 'openai' and no custom OPENAI_API_BASE_URL is set.")

        if self.LLM_PROVIDER == "azure_openai":
            if not all([self.AZURE_OPENAI_API_KEY, self.AZURE_OPENAI_ENDPOINT, self.AZURE_OPENAI_API_VERSION, self.AZURE_OPENAI_DEPLOYMENT_NAME]):
                raise ValueError("For LLM_PROVIDER 'azure_openai', all AZURE_OPENAI_API_KEY, AZURE_OPENAI_ENDPOINT, AZURE_OPENAI_API_VERSION, and AZURE_OPENAI_DEPLOYMENT_NAME must be set.")
            # If using Azure, LLM_MODEL should ideally match AZURE_OPENAI_DEPLOYMENT_NAME.
            # Or, we can enforce that LLM_MODEL is used as the deployment name here.
            # For now, assuming documentation will guide user to set LLM_MODEL = AZURE_OPENAI_DEPLOYMENT_NAME.

        if self.SEARCH_API == "tavily" and not self.TAVILY_API_KEY:
            raise ValueError("TAVILY_API_KEY is required when SEARCH_API is 'tavily'")

    def __str__(self):
        # Dynamically build the string representation
        config_details = [
            f"  LLM Provider: {self.LLM_PROVIDER}",
            f"  LLM Model: {self.LLM_MODEL}",
            f"  LLM Temperature: {self.LLM_TEMPERATURE}",
            f"  LLM Max Tokens: {self.LLM_MAX_TOKENS}",
        ]
        if self.LLM_PROVIDER == "openai" or self.OPENAI_API_BASE_URL: # Show relevant OpenAI details
            config_details.append(f"  OpenAI API Key: {'********' if self.OPENAI_API_KEY else 'Not Set'}")
            config_details.append(f"  OpenAI API Base URL: {self.OPENAI_API_BASE_URL if self.OPENAI_API_BASE_URL else 'Default'}")

        if self.LLM_PROVIDER == "azure_openai": # Show relevant Azure details
            config_details.extend([
                f"  Azure OpenAI API Key: {'********' if self.AZURE_OPENAI_API_KEY else 'Not Set'}",
                f"  Azure OpenAI Endpoint: {self.AZURE_OPENAI_ENDPOINT}",
                f"  Azure OpenAI API Version: {self.AZURE_OPENAI_API_VERSION}",
                f"  Azure OpenAI Deployment Name: {self.AZURE_OPENAI_DEPLOYMENT_NAME}",
            ])

        if self.LLM_PROVIDER == "ollama": # Show relevant Ollama details
             config_details.append(f"  Ollama Base URL: {self.OLLAMA_BASE_URL if self.OLLAMA_BASE_URL else 'Default'}")
             config_details.append(f"  Ollama Num Retries: {self.OLLAMA_NUM_RETRIES}")
             config_details.append(f"  Ollama Retry Delay Seconds: {self.OLLAMA_RETRY_DELAY_SECONDS}")

        config_details.extend([
            f"  Search API: {self.SEARCH_API}",
            f"  Max Research Loops: {self.MAX_RESEARCH_LOOPS}",
            f"  Max Search Results: {self.MAX_SEARCH_RESULTS_PER_QUERY}",
            f"  Output Filename: {self.OUTPUT_FILENAME}",
            f"  Interactive Mode: {self.INTERACTIVE_MODE}",
            f"  Summarization Chunk Size Chars: {self.SUMMARIZATION_CHUNK_SIZE_CHARS}",
            f"  Summarization Chunk Overlap Chars: {self.SUMMARIZATION_CHUNK_OVERLAP_CHARS}",
            f"  Use Snippets Only Mode: {self.USE_SNIPPETS_ONLY_MODE}",
            f"  Max Text Length per Source (Chars): {self.MAX_TEXT_LENGTH_PER_SOURCE_CHARS}",
            f"  Process PDF Files: {self.PROCESS_PDF_FILES}",
            f"  Log Level: {self.LOG_LEVEL}",
        ])
        return "Configuration:\n" + "\n".join(config_details)

# Example usage (optional, for testing)
if __name__ == "__main__":
    try:
        config = Configuration()
        print(config)
    except ValueError as e:
        print(f"Error: {e}")
