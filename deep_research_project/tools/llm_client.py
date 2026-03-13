from deep_research_project.config.config import Configuration
import logging
from typing import Type, TypeVar, Any, Optional
import asyncio
import json
import re
from pydantic import BaseModel, ValidationError
from langchain_core.messages import SystemMessage, HumanMessage
from deep_research_project.tools.cache_manager import CacheManager

logger = logging.getLogger(__name__)

T = TypeVar("T", bound=BaseModel)

class LLMPolicyError(Exception):
    """Exception raised when the LLM provider refuses to process a request due to safety or policy filters."""
    pass

class LLMClient:
    def __init__(self, config: Configuration):
        self.config = config
        self.llm = None
        self._rate_limit_lock = asyncio.Lock()
        self._last_request_time = 0.0
        cache_dir = getattr(self.config, "CACHE_DIR", ".cache")
        enable_caching = getattr(self.config, "ENABLE_CACHING", True)
        self.cache_manager = CacheManager(cache_dir=cache_dir, enabled=enable_caching)

        if self.config.LLM_PROVIDER == "openai":
            try:
                from langchain_openai import ChatOpenAI

                temperature = self.config.LLM_TEMPERATURE
                if self._is_fixed_temperature_model(self.config.LLM_MODEL):
                    logger.info(f"Model {self.config.LLM_MODEL} detected as requiring fixed temperature (1.0). Overriding.")
                    temperature = 1.0

                openai_kwargs = {
                    "model_name": self.config.LLM_MODEL,
                    "temperature": temperature,
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
        elif self.config.LLM_PROVIDER == "gemini":
            try:
                from langchain_google_genai import ChatGoogleGenerativeAI
                gemini_kwargs = {
                    "model": self.config.LLM_MODEL,
                    "temperature": self.config.LLM_TEMPERATURE,
                    "max_output_tokens": self.config.LLM_MAX_TOKENS,
                    "google_api_key": self.config.GOOGLE_API_KEY
                }
                self.llm = ChatGoogleGenerativeAI(**gemini_kwargs)
                logger.info(f"Initialized Gemini LLM Client with model: {self.config.LLM_MODEL}")
            except ImportError:
                logger.error("langchain_google_genai is not installed.")
                raise
            except Exception as e:
                logger.error(f"Error initializing ChatGoogleGenerativeAI: {e}", exc_info=True)
                raise
        elif self.config.LLM_PROVIDER == "placeholder_llm":
            logger.info("Initialized Placeholder LLM Client.")
            self.llm = "PlaceholderLLMInstance"
        else:
            logger.info(f"LLM Provider is '{self.config.LLM_PROVIDER}'. Using placeholder.")
            self.llm = "PlaceholderLLMInstance"

    async def _wait_for_rate_limit(self):
        """Waits to respect the rate limit before EACH request."""
        rpm = getattr(self.config, "LLM_RATE_LIMIT_RPM", 60)
        if not isinstance(rpm, (int, float)) or rpm <= 0:
            rpm = 60
        
        # Calculate interval to stay strictly below RPM
        # We add a 5% buffer to be safe
        limit_interval = (60.0 / rpm) * 1.05 

        async with self._rate_limit_lock:
            current_time = asyncio.get_event_loop().time()
            elapsed = current_time - self._last_request_time
            if elapsed < limit_interval:
                wait_time = limit_interval - elapsed
                logger.debug(f"Rate limit shielding: Sleeping for {wait_time:.3f}s (RPM: {rpm})")
                await asyncio.sleep(wait_time)
            self._last_request_time = asyncio.get_event_loop().time()

    async def _invoke_with_retry(self, func, *args, **kwargs):
        """Helper to invoke an async LLM function with exponential backoff retry logic."""
        max_retries = 3
        base_delay = getattr(self.config, "LLM_RETRY_BASE_DELAY", 2.0)
        
        for attempt in range(max_retries + 1):
            try:
                # Always wait for the rate limit shield before the call
                await self._wait_for_rate_limit()
                return await func(*args, **kwargs)
            except Exception as e:
                error_str = str(e).lower()
                is_rate_limit = "rate limit" in error_str or "429" in error_str
                is_policy_error = any(kw in error_str for kw in ["policy", "safety", "content_filter", "filtered", "blocked", "management"])

                if is_policy_error:
                    logger.warning(f"LLM call blocked by policy/safety filter: {e}")
                    raise LLMPolicyError(f"LLM Policy Violation: {e}")
                
                if attempt < max_retries and (is_rate_limit or "timeout" in error_str or "connection" in error_str):
                    delay = base_delay * (2 ** attempt)
                    logger.warning(f"LLM call failed (attempt {attempt+1}/{max_retries+1}): {e}. Retrying in {delay:.1f}s...")
                    await asyncio.sleep(delay)
                else:
                    if attempt == max_retries:
                        logger.error(f"LLM call failed after {max_retries+1} attempts: {e}")
                    raise

        return None # Should not be reached but better than recursion

    def _is_fixed_temperature_model(self, model_name: str) -> bool:
        """Checks if the model matches any of the patterns defined in the configuration
        for models requiring a fixed temperature (1.0)."""
        if not model_name or not hasattr(self.config, "FIXED_TEMPERATURE_MODELS"):
            return False

        patterns = [p.strip().lower() for p in self.config.FIXED_TEMPERATURE_MODELS.split(",") if p.strip()]
        model_name_lower = model_name.lower()

        return any(pattern in model_name_lower for pattern in patterns)

    async def generate_text(self, prompt: str, system_prompt: Optional[str] = None, temperature: Optional[float] = None) -> str:
        """Asynchronously generates text from a prompt with retry logic and caching."""
        if self._is_fixed_temperature_model(self.config.LLM_MODEL):
            if temperature is not None and temperature != 1.0:
                logger.info(f"Overriding provided temperature {temperature} to 1.0 for GPT-5 model.")
            temperature = 1.0

        cache_key = prompt
        if system_prompt:
            cache_key = f"SYSTEM: {system_prompt}\nUSER: {prompt}"

        if getattr(self.config, "ENABLE_CACHING", True):
            cached = await self.cache_manager.get_llm_cache(cache_key)
            if cached:
                logger.info("LLM result retrieved from cache.")
                return cached

        if self.llm == "PlaceholderLLMInstance":
            result = self._simulate_placeholder(prompt, system_prompt=system_prompt)
        else:
            async def _call():
                llm_to_call = self.llm
                if temperature is not None and hasattr(self.llm, "bind"):
                    llm_to_call = self.llm.bind(temperature=temperature)
                
                if system_prompt:
                    messages = [
                        SystemMessage(content=system_prompt),
                        HumanMessage(content=prompt)
                    ]
                    response = await llm_to_call.ainvoke(messages)
                else:
                    response = await llm_to_call.ainvoke(prompt)
                
                # Robustly extract content and handle potential list returns (e.g., from Gemini)
                content = None
                if hasattr(response, 'content'):
                    content = response.content
                else:
                    content = response
                
                if isinstance(content, list):
                    # Robustly handle list of strings or list of dictionaries (Common in some LLM providers like Gemini)
                    parts = []
                    for item in content:
                        if isinstance(item, dict):
                            # Try to extract common text fields
                            parts.append(str(item.get('text', item.get('content', str(item)))))
                        else:
                            parts.append(str(item))
                    return "\n".join(parts)
                elif isinstance(content, dict):
                    # Handle single dictionary response
                    return str(content.get('text', content.get('content', str(content))))
                elif content is None:
                    return ""
                return str(content)

            try:
                result = await self._invoke_with_retry(_call)
            except LLMPolicyError:
                logger.warning("LLM call suppressed due to policy violation in generate_text. Returning empty string.")
                return ""
        
        if getattr(self.config, "ENABLE_CACHING", True) and result:
            await self.cache_manager.set_llm_cache(cache_key, result)
        
        return result

    async def generate_structured(self, prompt: str, response_model: Type[T]) -> T:
        """Asynchronously generates structured output using LangChain's with_structured_output with robust fallbacks, retries, and caching."""
        if getattr(self.config, "ENABLE_CACHING", True):
            cached_json = await self.cache_manager.get_llm_cache(prompt)
            if cached_json:
                try:
                    logger.info(f"Structured result for {response_model.__name__} retrieved from cache.")
                    return response_model.model_validate_json(cached_json)
                except Exception as e:
                    logger.warning(f"Failed to validate cached JSON for {response_model.__name__}: {e}")

        if self.llm == "PlaceholderLLMInstance":
            result = self._simulate_placeholder_structured(prompt, response_model)
        else:
            async def _call_native():
                structured_llm = self.llm.with_structured_output(response_model)
                result = await structured_llm.ainvoke(prompt)
                if result:
                    return result
                else:
                    raise ValueError("LLM returned empty structured output")

            try:
                # Try native structured output with retry
                result = await self._invoke_with_retry(_call_native)
            except LLMPolicyError:
                logger.warning("LLM call suppressed due to policy violation in generate_structured. Falling back to robust extraction.")
                result = await self._generate_structured_fallback(prompt, response_model)
            except Exception as e:
                logger.warning(f"Native structured output failed even with retries, falling back to PydanticOutputParser: {e}")
                result = await self._generate_structured_fallback(prompt, response_model)
        
        if getattr(self.config, "ENABLE_CACHING", True) and result:
            await self.cache_manager.set_llm_cache(prompt, result.model_dump_json())
        
        return result

    async def _generate_structured_fallback(self, prompt: str, response_model: Type[T]) -> T:
        """Fallback that uses PydanticOutputParser and custom robust JSON extraction if parsing fails."""
        from langchain_core.output_parsers import PydanticOutputParser
        parser = PydanticOutputParser(pydantic_object=response_model)

        format_instructions = parser.get_format_instructions()
        full_prompt = f"{prompt}\n\n{format_instructions}"

        try:
            response_text = await self.generate_text(full_prompt)
        except LLMPolicyError:
            logger.error("Policy error during structured fallback. Attempting minimal recovery.")
            return self._robust_json_extract("", response_model)
        
        try:
            # Standard parsing
            return parser.parse(response_text)
        except Exception as e:
            logger.warning(f"Standard PydanticOutputParser failed: {e}. Attempting robust manual extraction.")
            return self._robust_json_extract(response_text, response_model)

    def _robust_json_extract(self, text: str, response_model: Type[T]) -> T:
        """Attempts to find and parse JSON even from messy LLM output, with field-level tolerance."""
        # Clean the text to find potential JSON blocks
        json_matches = re.findall(r'(\{.*\}|\[.*\])', text, re.DOTALL)
        
        parsed_data = {}
        for match in json_matches:
            try:
                data = json.loads(match)
                if isinstance(data, dict):
                    parsed_data.update(data)
                elif isinstance(data, list) and hasattr(response_model, 'model_fields'):
                    # If it's a list, check if the model has a list field that might fit
                    for field_name, field_info in response_model.model_fields.items():
                        # Check if annotation is a list (handling List[T] and list[T])
                        origin = getattr(field_info.annotation, '__origin__', None)
                        if origin is list or field_info.annotation is list:
                            parsed_data[field_name] = data
                            break
            except json.JSONDecodeError:
                continue

        if not parsed_data:
            logger.error(f"Failed to extract any valid JSON from: {text[:200]}...")
            try:
                # Try to create a minimal valid instance by fulfilling list fields
                min_data = {}
                if hasattr(response_model, 'model_fields'):
                    for field_name, field_info in response_model.model_fields.items():
                        origin = getattr(field_info.annotation, '__origin__', None)
                        if origin is list or field_info.annotation is list:
                            min_data[field_name] = []
                return response_model.model_validate(min_data)
            except ValidationError:
                raise ValueError(f"Could not generate {response_model.__name__} even with robust extraction.")

        # Final attempt to validate what we found
        try:
            return response_model.model_validate(parsed_data)
        except ValidationError as ve:
            logger.warning(f"Validation failed on extracted data: {ve}. Attempting partial recovery.")
            return self._partial_model_recovery(parsed_data, response_model)

    def _partial_model_recovery(self, data: dict, response_model: Type[T]) -> T:
        """Tries to recover a model by cleaning up list fields that failed validation."""
        cleaned_data = data.copy()
        
        if not hasattr(response_model, 'model_fields'):
            return response_model.model_validate(data)

        for field_name, field_info in response_model.model_fields.items():
            if field_name in data and isinstance(data[field_name], list):
                # Check if it's a list of BaseModels
                origin = getattr(field_info.annotation, '__origin__', None)
                args = getattr(field_info.annotation, '__args__', [])
                if (origin is list or field_info.annotation is list) and args and isinstance(args[0], type) and issubclass(args[0], BaseModel):
                    item_model = args[0]
                    valid_items = []
                    for item in data[field_name]:
                        try:
                            valid_items.append(item_model.model_validate(item))
                        except ValidationError:
                            logger.debug(f"Skipping invalid item in {field_name}: {item}")
                            continue
                    cleaned_data[field_name] = valid_items
        
        try:
            return response_model.model_validate(cleaned_data)
        except ValidationError:
            # Last resort: try to return a very basic instance
            return response_model.model_validate({})

    def _simulate_placeholder(self, prompt: str, system_prompt: Optional[str] = None) -> str:
        logger.debug(f"LLMClient (Placeholder) generating text for prompt: '{prompt[:80]}...' (System prompt present: {system_prompt is not None})")
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
