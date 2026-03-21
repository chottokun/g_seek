# Repository Specific Agent Guidelines (g_seek)

## Merging & Integration Workflow

1.  **Architecture First**: This project has migrated to a **LangGraph-based architecture**. 
    *   **CRITICAL**: Reject or manually refactor any PRs that rely on the legacy `ResearchLoop` class if they would degrade the current `deep_research_project/core/graph.py` structure.
    *   Always verify if a PR "downgrades" the UI logic (e.g., reverting to `streamlit_app.py` versions that don't support LangGraph states).

2.  **Verification Requirements**:
    *   **Unit Tests**: Must pass `uv run python3 -m unittest discover deep_research_project/tests/`.
    *   **UI Sanity Check**:
        *   Chainlit: `chainlit run deep_research_project/chainlit_app.py`
        *   Streamlit: `streamlit run deep_research_project/streamlit_app.py`
    *   **Interactive Mode**: Ensure `INTERACTIVE_MODE=False` in `config.py` for automated testing, but verify that setting it to `True` doesn't break the UI interrupt logic.

3.  **Conflict Resolution Strategy**:
    *   For `chainlit_app.py` and `graph.py`, prioritize the **HEAD** structure but cherry-pick the logic/optimizations from the PR. 
    *   Do not perform bulk merges (Octopus) on core files; merge one-by-one to ensure no "先祖返り" (regression to older versions) occurs.

4.  **Skills Registry**:
    *   Any changes to `skills_manager.py` or `graph.py` must maintain the project-local paths for `data/skills/static` and `data/skills/dynamic`.
