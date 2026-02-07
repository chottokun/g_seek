import os
from typing import Optional
from dotenv import load_dotenv
from pydantic import Field, AliasChoices, model_validator
from pydantic_settings import BaseSettings

# Load environment variables from .env file
# We keep this to ensure os.environ is populated for other parts of the application
# that might rely on os.getenv() finding values from .env.
load_dotenv()

class Configuration(BaseSettings):
    # LLM Configuration
    # LLM_PROVIDER: Specifies the LLM provider to use (e.g., "openai", "ollama", "azure_openai", "placeholder_llm").
    LLM_PROVIDER: str = Field(default="placeholder_llm")
    # LLM_MODEL: Specifies the model name for the selected provider.
    # For Azure OpenAI, this should be your DEPLOYMENT NAME.
    LLM_MODEL: str = Field(default="default_model_name")
    # LLM_TEMPERATURE: Controls randomness. Lower is more deterministic.
    LLM_TEMPERATURE: float = Field(default=0.7)
    # LLM_MAX_TOKENS: Maximum number of tokens to generate.
    LLM_MAX_TOKENS: int = Field(default=1024)

    # OpenAI Specific Configuration (also used for LiteLLM proxies)
    OPENAI_API_KEY: Optional[str] = Field(default=None)
    # OPENAI_API_BASE_URL: Optional. Use for OpenAI-compatible APIs (e.g., LiteLLM, local LLMs). If None, uses default OpenAI.
    OPENAI_API_BASE_URL: Optional[str] = Field(default=None, validation_alias=AliasChoices("OPENAI_API_BASE_URL", "OPENAI_BASE_URL"))

    # Azure OpenAI Specific Configuration: Required settings for using Azure OpenAI directly.
    AZURE_OPENAI_API_KEY: Optional[str] = Field(default=None)
    AZURE_OPENAI_ENDPOINT: Optional[str] = Field(default=None)
    # AZURE_OPENAI_API_VERSION: API version, e.g., "2023-12-01-preview".
    AZURE_OPENAI_API_VERSION: Optional[str] = Field(default=None)
    # AZURE_OPENAI_DEPLOYMENT_NAME: Your Azure deployment name (used as LLM_MODEL if provider is "azure_openai").
    AZURE_OPENAI_DEPLOYMENT_NAME: Optional[str] = Field(default=None)

    # Ollama Specific Configuration
    OLLAMA_BASE_URL: Optional[str] = Field(default=None)
    # Number of retries for Ollama connection errors, 0 means one attempt only.
    OLLAMA_NUM_RETRIES: int = Field(default=1)
    # Delay in seconds between retries for Ollama.
    OLLAMA_RETRY_DELAY_SECONDS: float = Field(default=2.0)

    # Search Configuration
    SEARCH_API: str = Field(default="duckduckgo")
    TAVILY_API_KEY: Optional[str] = Field(default=None)
    SEARXNG_BASE_URL: str = Field(default="http://localhost:8080")

    # Research Loop Configuration
    MAX_RESEARCH_LOOPS: int = Field(default=3)
    MAX_SEARCH_RESULTS_PER_QUERY: int = Field(default=3)

    # Output Configuration
    OUTPUT_FILENAME: str = Field(default="research_report.md")

    # Logging Configuration
    LOG_LEVEL: str = Field(default="INFO")

    # Interactive Mode Configuration
    INTERACTIVE_MODE: bool = Field(default=False)

    # Summarization Configuration
    SUMMARIZATION_CHUNK_SIZE_CHARS: int = Field(default=10000)
    SUMMARIZATION_CHUNK_OVERLAP_CHARS: int = Field(default=500)

    # Optimization Configuration
    # MAX_CONCURRENT_CHUNKS: Max number of chunk summarization tasks to run in parallel.
    MAX_CONCURRENT_CHUNKS: int = Field(default=5)
    # LLM_RATE_LIMIT_RPM: Max requests per minute to the LLM API.
    LLM_RATE_LIMIT_RPM: int = Field(default=60)

    USE_SNIPPETS_ONLY_MODE: bool = Field(default=False)
    MAX_TEXT_LENGTH_PER_SOURCE_CHARS: int = Field(default=0)
    PROCESS_PDF_FILES: bool = Field(default=True)

    # Additional configurations to avoid hard-coding
    RETRIEVAL_TIMEOUT: int = Field(default=15)
    USER_AGENT: str = Field(default="DeepResearchBot/1.0")
    SEARXNG_LANGUAGE: str = Field(default="ja")
    SEARXNG_SAFESEARCH: int = Field(default=1)
    SEARXNG_CATEGORIES: str = Field(default="general")
    RESEARCH_PLAN_MIN_SECTIONS: int = Field(default=3)
    RESEARCH_PLAN_MAX_SECTIONS: int = Field(default=5)
    MAX_QUERY_WORDS: int = Field(default=12)
    REPORT_DIR: str = Field(default="temp_reports")
    CLEANUP_AGE_SECONDS: int = Field(default=3600)
    DEFAULT_LANGUAGE: str = Field(default="Japanese")

    @model_validator(mode='after')
    def validate_config(self):
        # Normalize LOG_LEVEL to uppercase
        self.LOG_LEVEL = self.LOG_LEVEL.upper()

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

        # Validate summarization settings
        if self.SUMMARIZATION_CHUNK_SIZE_CHARS <= 0:
            raise ValueError("SUMMARIZATION_CHUNK_SIZE_CHARS must be positive.")
        if self.SUMMARIZATION_CHUNK_OVERLAP_CHARS < 0 or self.SUMMARIZATION_CHUNK_OVERLAP_CHARS >= self.SUMMARIZATION_CHUNK_SIZE_CHARS:
            # Instead of raising, we can force it to a safe value or just let the user know later.
            # But for initial config, raising is okay.
            raise ValueError("SUMMARIZATION_CHUNK_OVERLAP_CHARS must be non-negative and less than SUMMARIZATION_CHUNK_SIZE_CHARS.")

        return self

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
            f"  Max Concurrent Chunks: {self.MAX_CONCURRENT_CHUNKS}",
            f"  LLM Rate Limit RPM: {self.LLM_RATE_LIMIT_RPM}",
            f"  Use Snippets Only Mode: {self.USE_SNIPPETS_ONLY_MODE}",
            f"  Max Text Length per Source (Chars): {self.MAX_TEXT_LENGTH_PER_SOURCE_CHARS}",
            f"  Process PDF Files: {self.PROCESS_PDF_FILES}",
            f"  Retrieval Timeout: {self.RETRIEVAL_TIMEOUT}",
            f"  User Agent: {self.USER_AGENT}",
            f"  SearxNG Language: {self.SEARXNG_LANGUAGE}",
            f"  SearxNG SafeSearch: {self.SEARXNG_SAFESEARCH}",
            f"  SearxNG Categories: {self.SEARXNG_CATEGORIES}",
            f"  Research Plan Sections: {self.RESEARCH_PLAN_MIN_SECTIONS}-{self.RESEARCH_PLAN_MAX_SECTIONS}",
            f"  Max Query Words: {self.MAX_QUERY_WORDS}",
            f"  Report Directory: {self.REPORT_DIR}",
            f"  Cleanup Age (Seconds): {self.CLEANUP_AGE_SECONDS}",
            f"  Default Language: {self.DEFAULT_LANGUAGE}",
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
