from deep_research_project.config.config import Configuration
import logging

logger = logging.getLogger(__name__)

class LLMClient:
    def __init__(self, config: Configuration):
        self.config = config
        self.llm = None # Placeholder for the actual LLM client

        if self.config.LLM_PROVIDER == "openai":
            try:
                from langchain_openai import ChatOpenAI
                if not self.config.OPENAI_API_KEY:
                    logger.error("OpenAI API key not configured.")
                    raise ValueError("OpenAI API key not configured.")
                self.llm = ChatOpenAI(
                    api_key=self.config.OPENAI_API_KEY,
                    model_name=self.config.LLM_MODEL,
                    temperature=0.7,
                )
                logger.info(f"Initialized OpenAI LLM Client with model: {self.config.LLM_MODEL}")
            except ImportError:
                logger.error("langchain_openai is not installed. Please install it.")
                raise
        elif self.config.LLM_PROVIDER == "ollama":
            try:
                from langchain_community.llms import Ollama
                # base_url を config から取得し、Ollama に渡す
                ollama_kwargs = {"model": self.config.LLM_MODEL}
                if hasattr(self.config, "OLLAMA_BASE_URL") and self.config.OLLAMA_BASE_URL:
                    ollama_kwargs["base_url"] = self.config.OLLAMA_BASE_URL
                self.llm = Ollama(**ollama_kwargs)
                logger.info(f"Initialized Ollama LLM Client with model: {self.config.LLM_MODEL}, base_url: {ollama_kwargs.get('base_url', 'default')}")
            except ImportError:
                logger.error("langchain_community is not installed. Please install it.")
                raise
        elif self.config.LLM_PROVIDER == "placeholder_llm": # A default that doesn't require keys
            logger.info("Initialized Placeholder LLM Client.")
            self.llm = "PlaceholderLLMInstance"
        elif self.config.LLM_PROVIDER == "default_llm_provider": # From default config
             logger.info(f"LLM Provider set to '{self.config.LLM_PROVIDER}'. This is a placeholder and will simulate LLM calls.")
             self.llm = "PlaceholderLLMInstance"
        else:
            # Potentially, user has set a provider, but we don't have logic for it yet
            logger.info(f"LLM Provider is '{self.config.LLM_PROVIDER}'. Advanced configuration needed. Using placeholder.")
            self.llm = "PlaceholderLLMInstance"
        logger.debug(f"[LLMClient __init__] self.llm is: '{self.llm}' (Type: {type(self.llm)})")


    def generate_text(self, prompt: str, temperature: float = 0.7) -> str:
        logger.debug(f"[LLMClient generate_text] self.llm is: '{self.llm}' (Type: {type(self.llm)})")
        if self.llm == "PlaceholderLLMInstance":
            # Simulate LLM response for placeholder
            logger.debug(f"LLMClient (Placeholder) generating text for prompt (first 80 chars): '{prompt[:80]}...'")
            if "generate a concise search query" in prompt.lower():
                response = f"Simulated search query for: {prompt.split(':')[-1].strip()}"
                logger.debug(f"Placeholder LLM generated search query: {response}")
                return response
            elif "summarize the following information" in prompt.lower():
                response = "This is a simulated summary of the provided information."
                logger.debug(f"Placeholder LLM generated summary: {response}")
                return response
            elif "identify key knowledge gaps" in prompt.lower():
                # Simulate reflection: sometimes generate new query, sometimes 'None'
                if "loop 1" in prompt.lower() or "loop 2" in prompt.lower(): # crude way to vary output for testing
                     response = "Simulated refined query based on reflection."
                else: # Simulate ending condition
                     response = "None"
                logger.debug(f"Placeholder LLM generated reflection query: {response}")
                return response

            default_response = f"Simulated LLM response to: {prompt}"
            logger.debug(f"Placeholder LLM generated default response: {default_response}")
            return default_response

        # OpenAI LLM 実際の呼び出し
        if self.config.LLM_PROVIDER == "openai":
            logger.info(f"LLMClient generating text with OpenAI for prompt: '{prompt[:80]}...'")
            response = self.llm.invoke(prompt, temperature=temperature, max_tokens=self.config.LLM_MAX_TOKENS)
            return response.content if hasattr(response, 'content') else str(response)

        # Ollama LLM 実際の呼び出し
        if self.config.LLM_PROVIDER == "ollama":
            logger.info(f"LLMClient generating text with Ollama for prompt: '{prompt[:80]}...'")
            return self.llm(prompt)

        logger.error("Actual LLM client logic is not implemented yet.")
        raise NotImplementedError("Actual LLM client logic is not implemented yet.")

# Example Usage (for testing this module)
if __name__ == "__main__":
    # Basic logging for example usage
    logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(levelname)s - %(name)s - %(message)s')
    logger.info("Testing LLMClient...")
    try:
        # Create a dummy Configuration object for testing
        class MockConfiguration:
            LLM_PROVIDER = "placeholder_llm"
            LLM_MODEL = "test_model"
                LLM_MAX_TOKENS = 256 # Example value for testing
            OPENAI_API_KEY = None # Not needed for placeholder
            LOG_LEVEL = "DEBUG"

        mock_config = MockConfiguration()
        llm_client = LLMClient(config=mock_config)

        prompt1 = "Generate a concise search query for the topic: Quantum Computing"
        response1 = llm_client.generate_text(prompt1)
        logger.info(f"Prompt 1: {prompt1}\nResponse 1: {response1}\n")

        prompt2 = "Summarize the following information relevant to 'AI ethics': ..."
        response2 = llm_client.generate_text(prompt2)
        logger.info(f"Prompt 2: {prompt2}\nResponse 2: {response2}\n")

        prompt3 = "Current research topic: Cats\nAccumulated summary so far:\nCats are fluffy.\n\nBased on the summary, identify key knowledge gaps... Generate a new, specific search query... This is for loop 1."
        response3 = llm_client.generate_text(prompt3)
        logger.info(f"Prompt 3 (Reflection): {prompt3}\nResponse 3: {response3}\n")

        prompt4 = "Current research topic: Dogs\nAccumulated summary so far:\nDogs are loyal.\n\nBased on the summary, identify key knowledge gaps... Generate a new, specific search query... This is for loop 3."
        response4 = llm_client.generate_text(prompt4)
        logger.info(f"Prompt 4 (Reflection end): {prompt4}\nResponse 4: {response4}\n")


    except Exception as e:
        logger.error(f"Error in LLMClient example: {e}", exc_info=True)
