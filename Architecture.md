# Architecture

The Research Assistant has been modernized to follow a multi-stage, asynchronous, and structured research workflow.

## Core Workflow

1.  **Planning Phase**:
    - The LLM decomposes the research topic into a structured research plan consisting of multiple sections.
    - Utilizes LangChain's `with_structured_output` (supported by OpenAI, Azure, and Ollama) to ensure a reliable schema.
    - (Interactive Mode) Human-in-the-loop approval and editing of the plan.

2.  **Execution Phase (Async)**:
    - Each section is researched independently and sequentially (with future support for parallel execution).
    - Each section undergoes an iterative search/summarize/reflect cycle:
        - **Web Search**: Targeted queries generated per section.
        - **Content Retrieval**: Asynchronous fetching of HTML and PDF content.
        - **Chunked Summarization**: Long documents are split into chunks and summarized to capture key details.
        - **Reflection**: LLM evaluates if the section goals are met or if further searching is required.

3.  **Synthesis Phase**:
    - Aggregates the summaries from all researched sections.
    - Synthesizes a cohesive final report with strict citation requirements.
# Architecture

The Research Assistant has been modernized to follow a multi-stage, asynchronous, and structured research workflow.

## Core Workflow

1.  **Planning Phase**:
    - The LLM decomposes the research topic into a structured research plan consisting of multiple sections.
    - Utilizes LangChain's `with_structured_output` (supported by OpenAI, Azure, and Ollama) to ensure a reliable schema.
    - (Interactive Mode) Human-in-the-loop approval and editing of the plan.

2.  **Execution Phase (Async)**:
    - Each section is researched independently and sequentially (with future support for parallel execution).
    - Each section undergoes an iterative search/summarize/reflect cycle:
        - **Web Search**: Targeted queries generated per section.
        - **Content Retrieval**: Asynchronous fetching of HTML and PDF content.
        - **Chunked Summarization**: Long documents are split into chunks and summarized to capture key details.
        - **Reflection**: LLM evaluates if the section goals are met or if further searching is required.

3.  **Synthesis Phase**:
    - Aggregates the summaries from all researched sections.
    - Synthesizes a cohesive final report with strict citation requirements.
    - **Citations**: Information is attributed to sources using numbered in-text citations (e.g., [1], [2]) mapping to a "Sources" section.

## Tech Stack

- **Framework**: LangChain (v0.3+) for LLM orchestration and structured outputs.
- **Async Runtime**: Python `asyncio` for non-blocking I/O (searches, retrievals, LLM calls).
- **LLM Clients**: Support for OpenAI, Azure OpenAI, and Ollama (via `ChatOllama`). Includes robust features like rate limiting, concurrency control (Semaphore), and structured output fallback logic.

- **Search**: DuckDuckGo and SearxNG support.
- **Frontend**: Chainlit (Modern UI with interruption support) and Streamlit.
## Infrastructure & Environment

### Package Management with `uv`
The project leverages `uv` to ensure consistency across development environments. `uv.lock` guarantees that all contributors and production environments use the exact same versions of libraries.

### Dockerized Workflow
The `docker-compose.yaml` provides a ready-to-use environment that includes:
- **Research Assistant**: The main Python application (Streamlit UI).
- **SearxNG**: A privacy-respecting metasearch engine configured for the assistant's use.

## Data Structures

- `ResearchState`: Tracks the global research context, plan, current section, and findings.
- `SectionPlan`: Represents a single research objective within the larger plan.
- `SearchResult` / `Source`: Structured data for web findings and citations.
- `KnowledgeGraph`: Entities and relations extracted from summarized findings.
