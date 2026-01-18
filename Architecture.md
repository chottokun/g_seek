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
- **LLM Clients**: Support for OpenAI, Azure OpenAI, and Ollama (via `ChatOllama`).
- **Search**: DuckDuckGo and SearxNG support.
- **Frontend**: Streamlit for a responsive and interactive UI.
- **Parsing**: Pydantic v2 for data validation and schema definition.

## Data Structures

- `ResearchState`: Tracks the global research context, plan, current section, and findings.
- `SectionPlan`: Represents a single research objective within the larger plan.
- `SearchResult` / `Source`: Structured data for web findings and citations.
- `KnowledgeGraph`: Entities and relations extracted from summarized findings.
