# Deep Research Project

This project is a Python application that automates the process of deep research on a given topic. It is inspired by the concepts behind systems like LocalDeepResearcher and utilizes the LangChain library to orchestrate Large Language Models (LLMs) and search tools.

The application iteratively performs the following steps:
1.  Generates a search query based on the research topic.
2.  Performs a web search using the query.
3.  Summarizes the search results.
4.  Reflects on the accumulated summary to identify knowledge gaps and generate a new, refined query.
5.  Repeats this process for a configured number of iterations.
6.  Finally, it compiles all findings into a markdown report.

Currently, it uses a placeholder LLM for language generation tasks and DuckDuckGo for web search.

## Setup

1.  **Clone the repository (or ensure the code is in its own directory):**
    ```bash
    # If this were a git repo, you'd clone it. For now, just navigate to the project directory.
    cd path/to/deep_research_project
    ```

2.  **Create a virtual environment:**
    It's highly recommended to use a virtual environment to manage dependencies.
    ```bash
    python -m venv venv
    ```

3.  **Activate the virtual environment:**
    *   On Windows:
        ```bash
        .\venv\Scripts\activate
        ```
    *   On macOS and Linux:
        ```bash
        source venv/bin/activate
        ```

4.  **Install dependencies:**
    ```bash
    pip install -r requirements.txt
    ```

## Configuration

The application uses environment variables for configuration, loaded from a `.env` file.

1.  **Create a `.env` file:**
    Copy the example configuration file to `.env`:
    ```bash
    cp .env.example .env
    ```

2.  **Edit `.env`:**
    Open the `.env` file and customize the settings as needed. Key variables include:
    *   `LLM_PROVIDER`: Specifies the LLM provider. Defaults to `placeholder_llm`. If you change this to `openai` or another provider, you will need to configure API keys (e.g., `OPENAI_API_KEY`).
    *   `LLM_MODEL`: The specific model to use for the selected provider.
    *   `SEARCH_API`: Specifies the search API. Defaults to `duckduckgo`. If you change to `tavily`, set `TAVILY_API_KEY`.
    *   `MAX_RESEARCH_LOOPS`: Number of research iterations.
    *   `MAX_SEARCH_RESULTS_PER_QUERY`: Number of search results to fetch per query.
    *   `OUTPUT_FILENAME`: Name of the file where the final report will be saved.
    *   `LOG_LEVEL`: Sets the application's logging level (e.g., `INFO`, `DEBUG`).

    For the default placeholder setup, you don't need to set any API keys.

## Running the Application

To run the application, execute the `main.py` script as a module from the parent directory of `deep_research_project` (if your project root is `deep_research_project` itself, you'd run it from within `deep_research_project` but refer to `main` directly, or if `deep_research_project` is a package inside a larger structure, adjust accordingly).

Assuming your current directory is `deep_research_project/`:
```bash
python main.py
```
Or, if `deep_research_project` is intended to be a package and you are in its parent directory:
```bash
python -m deep_research_project.main
```
The latter is generally more robust for Python projects structured as packages. The application will log its progress to the console and, upon completion, save the research report to the file specified by `OUTPUT_FILENAME` (default: `research_report.md`).

## Project Structure
```
deep_research_project/
├── config/                 # Configuration files (config.py)
│   └── config.py
├── core/                   # Core logic (research_loop.py, state.py)
│   ├── research_loop.py
│   └── state.py
├── tools/                  # LLM and Search client integrations
│   ├── llm_client.py
│   └── search_client.py
├── main.py                 # Main application entry point
├── requirements.txt        # Project dependencies
├── .env.example            # Example environment variables
└── README.md               # This file
```
