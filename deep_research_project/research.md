# Deep Research Project

This project is a sophisticated AI agent that automates deep research. It decomposes a research topic into multiple sections, processes them using iterative search and reflection, and synthesizes a structured report with citations.

## Key Features

1.  **Iterative Research Cycle**: Generates queries, performs searches, summarizes content, and reflects on findings to decide if more research is needed for each section.
2.  **Modern Async Stack**: Built using `asyncio` and LangChain 0.3+ for high performance and responsiveness.
3.  **Real-time Progress Display**: The Streamlit UI provides live updates on the research status of each section.
4.  **Citations & Sources**: Automatically generates reports with numbered citations mapping to original sources.

## Setup & Running

We use **uv** for dependency management.

### 1. Installation

```bash
uv sync
```

### 2. Configuration

Create a `.env` file in the root directory:
```bash
cp .env.example .env
```

Key variables:
- `LLM_PROVIDER`: `ollama`, `openai`, or `azure`.
- `SEARCH_API`: `searxng` or `duckduckgo`.
- `MAX_RESEARCH_LOOPS`: Controls how many times the agent iterates per section.

### 3. Execution

#### Streamlit UI
```bash
uv run streamlit run deep_research_project/streamlit_app.py
```

#### CLI
```bash
uv run -m deep_research_project.main
```

## Project Structure
```
deep_research_project/
├── config/                 # Configuration management (Configuration class)
├── core/                   # Orchestration logic
│   ├── research_loop.py    # Main async agent loop
│   └── state.py            # Pydantic state models
├── tools/                  # LLM and Search interface
│   ├── llm_client.py       # ChatModel wrappers
│   ├── search_client.py    # Search API wrappers
│   └── content_retriever.py# Web scraping and PDF parsing
├── tests/                  # Async unit and integration tests
├── main.py                 # CLI entry point
└── streamlit_app.py        # Streamlit frontend
```
