import streamlit as st
import sys
import os

# Adjust path to import from sibling directories
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from deep_research_project.config.config import Configuration
from deep_research_project.core.state import ResearchState
from deep_research_project.core.research_loop import ResearchLoop # Will be used later

def main():
    st.set_page_config(layout="wide", page_title="Deep Research Assistant")
    st.title("Deep Research Assistant")

    # Initialize session state variables if they don't exist
    if "research_topic" not in st.session_state:
        st.session_state.research_topic = ""
    if "research_state" not in st.session_state:
        st.session_state.research_state = None
    if "research_loop" not in st.session_state: # Added for research_loop
        st.session_state.research_loop = None
    if "messages" not in st.session_state:
        st.session_state.messages = [] # For displaying status or logs
    if "selected_sources" not in st.session_state: # For search result selection
        st.session_state.selected_sources = {}

    # Sidebar for controls
    with st.sidebar:
        st.header("Controls")
        research_topic_input = st.text_input(
            "Enter Research Topic:",
            value=st.session_state.research_topic,
            key="topic_input"
        )

        if st.button("Start Research", key="start_button"):
            if research_topic_input:
                st.session_state.research_topic = research_topic_input
                st.session_state.messages = [{"role": "assistant", "content": f"Starting research for: {st.session_state.research_topic}"}]

                # Initialize Configuration and ResearchState
                try:
                    config = Configuration()
                    st.session_state.research_state = ResearchState(research_topic=st.session_state.research_topic)
                    st.session_state.research_loop = ResearchLoop(config, st.session_state.research_state)
                    st.session_state.messages.append({"role": "assistant", "content": "Research initialized."})

                    # Trigger initial query generation
                    st.session_state.messages.append({"role": "assistant", "content": "Generating initial query..."})
                    st.session_state.research_loop._generate_initial_query()
                    st.session_state.messages.append({"role": "assistant", "content": f"Initial query proposed: {st.session_state.research_state.proposed_query}"})
                    st.experimental_rerun() # Rerun to update UI with proposed query

                except Exception as e:
                    st.error(f"Error during initialization or initial query generation: {e}")
                    st.session_state.messages.append({"role": "assistant", "content": f"Error: {e}"})
                    # Reset state if loop initialization fails
                    st.session_state.research_state = None
                    st.session_state.research_loop = None
            else:
                st.warning("Please enter a research topic.")

        st.subheader("Status:")
        # Display messages/logs
        # Make sure messages list is always available
        if "messages" not in st.session_state:
            st.session_state.messages = []

        for message in st.session_state.messages:
            with st.chat_message(message["role"]):
                st.markdown(message["content"])


    # Main area for displaying research content
    st.header("Research Output")

    if st.session_state.research_state:
        # Display current topic and active query
        st.subheader("Current State:")
        st.text(f"Topic: {st.session_state.research_state.research_topic}")
        if st.session_state.research_state.current_query:
            st.info(f"Current Active Query: {st.session_state.research_state.current_query}")

        # --- Query Proposal and Approval ---
        st.markdown("---")
        st.subheader("1. Query Management")
        if st.session_state.research_state.proposed_query:
            edited_query = st.text_area(
                "Edit proposed query if needed:",
                value=st.session_state.research_state.proposed_query,
                key="edited_query_text_area",
                height=100
            )
            if st.button("Approve and Use Query", key="approve_query_button"):
                if edited_query:
                    st.session_state.research_state.current_query = edited_query
                    st.session_state.research_state.proposed_query = None
                    # Reset search_results when a new query is approved to allow new search
                    st.session_state.research_state.search_results = None
                    st.session_state.research_state.pending_source_selection = False
                    st.session_state.messages.append({"role": "user", "content": f"Query approved: {edited_query}"})
                    st.experimental_rerun()
                else:
                    st.warning("Cannot approve an empty query.")
        elif st.session_state.research_state.current_query:
            st.success(f"Query approved and active: {st.session_state.research_state.current_query}")
        else:
            st.info("No query proposed or active. Start research or wait for initial query generation.")

        # --- Web Search Triggering ---
        if st.session_state.research_state.current_query and \
           not st.session_state.research_state.search_results and \
           not st.session_state.research_state.pending_source_selection:
            try:
                st.session_state.messages.append({"role": "assistant", "content": f"Performing web search for: {st.session_state.research_state.current_query}"})
                st.session_state.research_loop._web_search() # This will set search_results and pending_source_selection
                st.session_state.messages.append({"role": "assistant", "content": f"Web search completed. Found {len(st.session_state.research_state.search_results) if st.session_state.research_state.search_results else 0} results."})
                st.experimental_rerun()
            except Exception as e:
                st.error(f"Error during web search: {e}")
                st.session_state.messages.append({"role": "assistant", "content": f"Error during web search: {e}"})

        # --- Search Results Display and Selection ---
        st.markdown("---")
        st.subheader("2. Source Selection")
        if st.session_state.research_state.pending_source_selection and st.session_state.research_state.search_results:
            st.info("Select sources from the search results below to include in the summary.")

            # Ensure selected_sources is initialized for this selection instance
            # This check helps if we re-enter this state without clearing selected_sources from a previous error.
            # However, st.session_state.selected_sources is globally initialized now.
            # We might want to clear it specifically when pending_source_selection becomes true if it's not empty.
            # For now, relying on the global init and clearing after "Summarize" button.

            for i, result in enumerate(st.session_state.research_state.search_results):
                checkbox_key = f"source_{result['link']}" # Use link as it's more likely unique
                # Initialize checkbox state if not already set
                if checkbox_key not in st.session_state.selected_sources:
                     st.session_state.selected_sources[checkbox_key] = False # Default to not selected

                is_selected = st.checkbox(
                    f"{result['title']}",
                    key=checkbox_key,
                    value=st.session_state.selected_sources[checkbox_key], # Persist state across reruns
                    on_change=lambda key=checkbox_key: st.session_state.selected_sources.update({key: st.session_state[key]})
                )
                # st.session_state.selected_sources[checkbox_key] = is_selected # Update based on interaction
                st.caption(f"{result['link']}")
                st.markdown(f"<small>{result['snippet']}</small>", unsafe_allow_html=True)
                st.markdown("---")

            if st.button("Summarize Selected Sources", key="summarize_button"):
                actual_selected_results = []
                for result in st.session_state.research_state.search_results:
                    if st.session_state.selected_sources.get(f"source_{result['link']}", False):
                        actual_selected_results.append(result)

                if actual_selected_results:
                    st.session_state.messages.append({"role": "user", "content": f"Summarizing {len(actual_selected_results)} selected sources..."})
                    try:
                        st.session_state.research_loop._summarize_sources(selected_results=actual_selected_results)
                        st.session_state.messages.append({"role": "assistant", "content": "Summarization complete."})
                        # research_loop._summarize_sources now sets pending_source_selection to False
                    except Exception as e:
                        st.error(f"Error during summarization: {e}")
                        st.session_state.messages.append({"role": "assistant", "content": f"Error during summarization: {e}"})
                else:
                    st.warning("No sources selected for summarization. Click checkboxes to select.")
                    # User clicked "Summarize" but selected nothing, so we are no longer pending selection for THIS set of results.
                    # However, if they want to select again from the same results, we should not set pending_source_selection to False here.
                    # The _summarize_sources method in research_loop handles setting pending_source_selection to False.
                    # If no sources selected, we just don't call it.
                    # Let's add a message and keep pending_source_selection True.
                    st.session_state.messages.append({"role": "assistant", "content": "No sources were selected. Please select at least one source to proceed with summarization."})


                # Clear selection dict for next round, regardless of whether summarization happened or not,
                # as the user has "submitted" their selection (or lack thereof) for this batch.
                st.session_state.selected_sources = {}
                st.experimental_rerun()
        elif st.session_state.research_state.search_results and not st.session_state.research_state.pending_source_selection:
             st.success("Sources have been processed (summarized or skipped). Ready for next reflection or new query.")


        # --- Summary Display ---
        st.markdown("---")
        st.subheader("3. Research Summaries")
        if st.session_state.research_state.new_information:
            st.markdown("#### Latest Findings:")
            st.info(st.session_state.research_state.new_information)

        if st.session_state.research_state.accumulated_summary:
            with st.expander("View Accumulated Research Summary"):
                st.markdown(st.session_state.research_state.accumulated_summary)
        else:
            st.info("No summary available yet.")

        st.markdown("---")
        st.subheader("4. Knowledge Graph (Placeholder)")
        # graph_area = st.empty() # Will display the graph

    else:
        st.info("Enter a research topic and click 'Start Research' to begin.")

if __name__ == "__main__":
    # To run streamlit, you'd typically use `streamlit run deep_research_project/streamlit_app.py`
    # This main guard is here for completeness but direct execution might need path adjustments
    # depending on how it's run. For development, use the CLI command.
    main()
