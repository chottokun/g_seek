from deep_research_project.config.config import Configuration
import logging
from typing import Type, TypeVar, Any, Optional
import asyncio
from pydantic import BaseModel

logger = logging.getLogger(__name__)

T = TypeVar("T", bound=BaseModel)

class LLMClient:
    def __init__(self, config: Configuration):
        self.config = config
        self.llm = None
        self._rate_limit_lock = asyncio.Lock()
        self._last_request_time = 0.0

        if self.config.LLM_PROVIDER == "openai":
            try:
                from langchain_openai import ChatOpenAI
                openai_kwargs = {
                    "model_name": self.config.LLM_MODEL,
                    "temperature": self.config.LLM_TEMPERATURE,
                    "max_tokens": self.config.LLM_MAX_TOKENS
                }
                if self.config.OPENAI_API_KEY:
                    openai_kwargs["api_key"] = self.config.OPENAI_API_KEY
                if self.config.OPENAI_API_BASE_URL:
                    openai_kwargs["base_url"] = self.config.OPENAI_API_BASE_URL

                self.llm = ChatOpenAI(**openai_kwargs)
                logger.info(f"Initialized OpenAI LLM Client with model: {self.config.LLM_MODEL}")

            except ImportError:
                logger.error("langchain_openai is not installed.")
                raise
            except Exception as e:
                logger.error(f"Error initializing ChatOpenAI: {e}", exc_info=True)
                raise

        elif self.config.LLM_PROVIDER == "azure_openai":
            try:
                from langchain_openai import AzureChatOpenAI
                azure_kwargs = {
                    "azure_endpoint": self.config.AZURE_OPENAI_ENDPOINT,
                    "api_key": self.config.AZURE_OPENAI_API_KEY,
                    "api_version": self.config.AZURE_OPENAI_API_VERSION,
                    "azure_deployment": self.config.AZURE_OPENAI_DEPLOYMENT_NAME,
                    "temperature": self.config.LLM_TEMPERATURE,
                    "max_tokens": self.config.LLM_MAX_TOKENS
                }
                self.llm = AzureChatOpenAI(**azure_kwargs)
                logger.info(f"Initialized Azure OpenAI Client with deployment: {self.config.AZURE_OPENAI_DEPLOYMENT_NAME}")
            except ImportError:
                logger.error("langchain_openai is not installed for Azure.")
                raise
            except Exception as e:
                logger.error(f"Error initializing AzureChatOpenAI: {e}", exc_info=True)
                raise

        elif self.config.LLM_PROVIDER == "ollama":
            try:
                from langchain_ollama import ChatOllama

                ollama_kwargs = {
                    "model": self.config.LLM_MODEL,
                    "temperature": self.config.LLM_TEMPERATURE,
                    "num_predict": self.config.LLM_MAX_TOKENS
                }
                if hasattr(self.config, "OLLAMA_BASE_URL") and self.config.OLLAMA_BASE_URL:
                    ollama_kwargs["base_url"] = self.config.OLLAMA_BASE_URL

                self.llm = ChatOllama(**ollama_kwargs)
                logger.info(f"Initialized Ollama LLM Client (ChatOllama) with model: {self.config.LLM_MODEL}")
            except ImportError:
                logger.error("langchain_ollama is not installed.")
                raise
        elif self.config.LLM_PROVIDER == "placeholder_llm":
            logger.info("Initialized Placeholder LLM Client.")
            self.llm = "PlaceholderLLMInstance"
        else:
            logger.info(f"LLM Provider is '{self.config.LLM_PROVIDER}'. Using placeholder.")
            self.llm = "PlaceholderLLMInstance"

    async def _wait_for_rate_limit(self):
        """Waits to respect the rate limit."""
        limit_interval = 60.0 / self.config.LLM_RATE_LIMIT_RPM if self.config.LLM_RATE_LIMIT_RPM > 0 else 0

        async with self._rate_limit_lock:
            loop = asyncio.get_running_loop()
            current_time = loop.time()
            time_since_last = current_time - self._last_request_time
            if time_since_last < limit_interval:
                await asyncio.sleep(limit_interval - time_since_last)
            self._last_request_time = loop.time()

    async def generate_text(self, prompt: str, temperature: Optional[float] = None) -> str:
        """Asynchronously generates text from a prompt."""
        await self._wait_for_rate_limit()

        if self.llm == "PlaceholderLLMInstance":
            return self._simulate_placeholder(prompt)

        try:
            # temperature override if provided
            llm_to_call = self.llm
            if temperature is not None and hasattr(self.llm, "bind"):
                # Use bind to override parameters for this specific call
                llm_to_call = self.llm.bind(temperature=temperature)

            response = await llm_to_call.ainvoke(prompt)
            if hasattr(response, 'content'):
                return response.content
            return str(response)
        except Exception as e:
            logger.error(f"Error during LLM ainvoke: {e}", exc_info=True)
            raise

    async def generate_structured(self, prompt: str, response_model: Type[T]) -> T:
        """Asynchronously generates structured output using LangChain's with_structured_output."""
        await self._wait_for_rate_limit()

        if self.llm == "PlaceholderLLMInstance":
            return self._simulate_placeholder_structured(prompt, response_model)

        try:
            structured_llm = self.llm.with_structured_output(response_model)
            return await structured_llm.ainvoke(prompt)
        except Exception as e:
            logger.warning(f"Native structured output failed, falling back to PydanticOutputParser: {e}")
            return await self._generate_structured_fallback(prompt, response_model)

    async def _generate_structured_fallback(self, prompt: str, response_model: Type[T]) -> T:
        from langchain_core.output_parsers import PydanticOutputParser
        parser = PydanticOutputParser(pydantic_object=response_model)

        format_instructions = parser.get_format_instructions()
        full_prompt = f"{prompt}\n\n{format_instructions}"

        response_text = await self.generate_text(full_prompt)
        return parser.parse(response_text)

    def _simulate_placeholder(self, prompt: str) -> str:
        logger.debug(f"LLMClient (Placeholder) generating text for prompt: '{prompt[:80]}...'")
        if "evaluate if the summary has sufficiently explored" in prompt.lower():
            return "EVALUATION: CONCLUDE\nQUERY: None"
        return f"Simulated LLM response to: {prompt[:50]}..."

    def _simulate_placeholder_structured(self, prompt: str, response_model: Type[T]) -> T:
        logger.debug(f"LLMClient (Placeholder) generating structured output for: {response_model.__name__}")

        if "structured research plan" in prompt.lower():
            from deep_research_project.core.state import ResearchPlanModel, Section
            return ResearchPlanModel(sections=[
                Section(title="Introduction", description="Overview of the topic"),
                Section(title="Current State", description="Latest trends"),
                Section(title="Conclusion", description="Final thoughts")
            ])
        elif "identify key entities" in prompt.lower():
            from deep_research_project.core.state import KnowledgeGraphModel, KGNode, KGEdge
            return KnowledgeGraphModel(
                nodes=[KGNode(id="n1", label="Entity 1", type="Concept")],
                edges=[KGEdge(source="n1", target="n1", label="related to")]
            )

        return response_model.model_validate({})
