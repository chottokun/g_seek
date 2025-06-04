import os
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

class Configuration:
    # LLM Configuration
    LLM_PROVIDER = os.getenv("LLM_PROVIDER", "placeholder_llm")  # e.g., "openai", "ollama"
    LLM_MODEL = os.getenv("LLM_MODEL", "default_model_name") # e.g., "gpt-3.5-turbo", "llama3"
    OPENAI_API_KEY = os.getenv("OPENAI_API_KEY") # Only needed if LLM_PROVIDER is openai

    # Search Configuration
    SEARCH_API = os.getenv("SEARCH_API", "duckduckgo") # e.g., "duckduckgo", "tavily"
    TAVILY_API_KEY = os.getenv("TAVILY_API_KEY") # Only needed if SEARCH_API is tavily

    # Research Loop Configuration
    MAX_RESEARCH_LOOPS = int(os.getenv("MAX_RESEARCH_LOOPS", "3"))
    MAX_SEARCH_RESULTS_PER_QUERY = int(os.getenv("MAX_SEARCH_RESULTS_PER_QUERY", "3"))

    # Output Configuration
    OUTPUT_FILENAME = os.getenv("OUTPUT_FILENAME", "research_report.md")

    # Logging Configuration
    LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()

    def __init__(self):
        # Perform any validation or conditional setup if needed
        if self.LLM_PROVIDER == "openai" and not self.OPENAI_API_KEY:
            raise ValueError("OPENAI_API_KEY is required when LLM_PROVIDER is 'openai'")
        if self.SEARCH_API == "tavily" and not self.TAVILY_API_KEY:
            raise ValueError("TAVILY_API_KEY is required when SEARCH_API is 'tavily'")

    def __str__(self):
        return (
            f"Configuration:\n"
            f"  LLM Provider: {self.LLM_PROVIDER}\n"
            f"  LLM Model: {self.LLM_MODEL}\n"
            f"  Search API: {self.SEARCH_API}\n"
            f"  Max Research Loops: {self.MAX_RESEARCH_LOOPS}\n"
            f"  Max Search Results: {self.MAX_SEARCH_RESULTS_PER_QUERY}\n"
            f"  Output Filename: {self.OUTPUT_FILENAME}"
        )

# Example usage (optional, for testing)
if __name__ == "__main__":
    try:
        config = Configuration()
        print(config)
    except ValueError as e:
        print(f"Error: {e}")
