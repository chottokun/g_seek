# Improvements and Refactoring Summary

This document details the major improvements and refactoring points implemented to transition the Research Assistant to a modern, multi-stage "Deep Research" architecture.

## 1. Architectural Shift: Multi-Stage Workflow

The system was refactored from a simple, single-topic iterative loop into a structured three-phase pipeline:

- **Planning Phase**: Instead of immediate searching, the LLM first analyzes the topic and decomposes it into distinct research sections. This ensures better coverage and prevents repetitive searching.
- **Execution Phase**: Each section is researched independently using its own search/summarize/reflect cycle. This allows for focused "deep dives" into specific sub-topics.
- **Synthesis Phase**: The findings from all sections are aggregated and synthesized into a cohesive final report, rather than relying on a continuously appended summary.

## 2. Modern Implementation Patterns

### Asynchronous Programming (`async/await`)
- **Refactoring**: All core components (`LLMClient`, `SearchClient`, `ContentRetriever`, and `ResearchLoop`) were refactored to be asynchronous.
- **Benefits**: Improved performance during I/O bound operations (fetching web pages, calling LLM APIs, searching) and a more responsive UI.

### Structured Output with LangChain & Pydantic v2
- **Refactoring**: Replaced manual JSON parsing and string manipulation with LangChain's `with_structured_output` API and Pydantic v2 models.
- **Models**: Defined `ResearchPlanModel`, `KnowledgeGraphModel`, and associated sub-models (`Section`, `KGNode`, `KGEdge`).
- **Benefits**: Reliable data extraction, automatic validation, and clear schema definitions.

### Library Modernization
- Updated to the latest versions of core libraries:
    - `langchain` / `langchain-core` (v0.3+)
    - `pydantic` (v2.x)
    - `httpx` (async replacement for `requests`)
    - `langchain-openai`, `langchain-ollama`

## 3. Enhanced Research Quality

### Strict Citation Enforcement
- **Improvement**: Updated the synthesis prompt to strictly require numbered in-text citations (e.g., `[1]`, `[2]`).
- **Implementation**: The LLM is provided with an indexed list of all gathered sources, and the final report synthesis logic enforces mapping claims back to these indices.
- **Result**: More credible and verifiable research reports.

### Knowledge Graph Extraction
- **Improvement**: Transitioned KG extraction to use the structured output pattern, ensuring that entities and relationships are consistently formatted as valid JSON objects.

## 4. Testing & Verification

### Async Unit Testing
- **Refactoring**: Converted the test suite to use `unittest.IsolatedAsyncioTestCase`.
- **Coverage**: Added detailed tests for async LLM calls, structured output parsing, and the multi-section research loop.

### UI Verification
- **Improvement**: Implemented Playwright scripts to automatically verify both "Automated" and "Interactive" research modes in Streamlit, capturing screenshots for visual confirmation.

## 5. Summary of Refactored Files

| File | Key Refactoring Points |
| :--- | :--- |
| `core/state.py` | Added Pydantic models and multi-section state tracking. |
| `core/research_loop.py` | Refactored to `async`, implemented Planning and Synthesis phases. |
| `tools/llm_client.py` | Refactored to `async`, added structured output support. |
| `tools/search_client.py` | Refactored to `async` (using `run_in_executor` for sync wrappers). |
| `tools/content_retriever.py` | Refactored to `async` using `httpx`, improved PDF extraction. |
| `streamlit_app.py` | Updated to handle async backend and plan approval UI. |
| `main.py` | Updated for `asyncio.run()`. |
| `tests/` | Modernized for async testing. |
