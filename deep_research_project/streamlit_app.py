import streamlit as st
import sys
import os

# Adjust path to import from sibling directories
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from deep_research_project.config.config import Configuration
from deep_research_project.core.state import ResearchState
from deep_research_project.core.research_loop import ResearchLoop # Will be used later
from streamlit_agraph import agraph, Node, Edge, Config # Corrected import

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
    if "run_interactive_in_streamlit" not in st.session_state:
        st.session_state.run_interactive_in_streamlit = False # Default to OFF
    if "use_snippets_only_mode" not in st.session_state:
        st.session_state.use_snippets_only_mode = False # Default to OFF

    # Sidebar for controls
    with st.sidebar:
        st.header("Controls")
        st.session_state.run_interactive_in_streamlit = st.toggle(
            "Run Interactively?",
            value=st.session_state.run_interactive_in_streamlit,
            key="interactive_mode_toggle",
            help="If ON, the system will pause for your approval for queries and source selections. If OFF, it will run automatically."
        )
        st.session_state.use_snippets_only_mode = st.toggle(
            "Use Snippets Only?",
            value=st.session_state.use_snippets_only_mode,
            key="snippets_only_toggle",
            help="If ON, the system will only use search result snippets for summarization, skipping full web page downloads. This is faster but may be less comprehensive."
        )
        st.markdown("---") # Add a separator
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
                    # Override INTERACTIVE_MODE based on Streamlit toggle
                    config.INTERACTIVE_MODE = st.session_state.run_interactive_in_streamlit
                    # Set USE_SNIPPETS_ONLY_MODE based on Streamlit toggle
                    config.USE_SNIPPETS_ONLY_MODE = st.session_state.use_snippets_only_mode

                    st.session_state.research_state = ResearchState(research_topic=st.session_state.research_topic)
                    # Pass the modified config to ResearchLoop
                    st.session_state.research_loop = ResearchLoop(config, st.session_state.research_state)

                    mode_message = "interactively" if config.INTERACTIVE_MODE else "non-interactively (automated)"
                    st.session_state.messages.append({"role": "assistant", "content": f"Research initialized to run {mode_message}."})

                    if config.USE_SNIPPETS_ONLY_MODE:
                        st.session_state.messages.append({"role": "assistant", "content": "Snippet-only mode is ON: Full content download will be skipped."})
                    else:
                        st.session_state.messages.append({"role": "assistant", "content": "Snippet-only mode is OFF: Attempting to download full content."})

                    if not config.INTERACTIVE_MODE:
                        st.session_state.messages.append({"role": "assistant", "content": "Research running automatically..."})
                        with st.spinner("Automated research in progress... Please wait."): # Show spinner during run_loop
                            st.session_state.research_loop.run_loop()
                        st.session_state.messages.append({"role": "assistant", "content": "Automated research complete."})
                        st.rerun() # Refresh UI to show final results
                    else:
                        # Interactive mode: Trigger initial query generation
                        st.session_state.messages.append({"role": "assistant", "content": "Generating initial query..."})
                        st.session_state.research_loop._generate_initial_query()
                        st.session_state.messages.append({"role": "assistant", "content": f"Initial query proposed: {st.session_state.research_state.proposed_query}"})
                        st.rerun() # Rerun to update UI for interactive steps

                except Exception as e:
                    st.error(f"Error during research process: {e}")
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
        research_state = st.session_state.research_state # Alias for convenience

        # Display current topic
        st.subheader("Current State:")
        st.text(f"Topic: {research_state.research_topic}")

        # If a final report exists, it means an automated run likely completed, or interactive run finished.
        if research_state.final_report:
            st.success("Research process complete. Final report generated.")
            # Optionally, display the last active query if available from the completed run
            if research_state.current_query: # This might be None if loop ended without a query
                 st.info(f"Last Active Query: {research_state.current_query}")
        elif research_state.current_query : # Interactive run, query active
            st.info(f"Current Active Query: {research_state.current_query}")


        # --- Interactive Controls (Query Management & Source Selection) ---
        # These sections are primarily for interactive mode.
        # If final_report exists, these steps are already done.
        if st.session_state.research_loop and st.session_state.research_loop.interactive_mode and not research_state.final_report:
            st.markdown("---")
            st.subheader("1. Query Management")
            if research_state.proposed_query:
                edited_query = st.text_area(
                    "Edit proposed query if needed:",
                    value=research_state.proposed_query,
                    key="edited_query_text_area",
                    height=100
                )
                if st.button("Approve and Use Query", key="approve_query_button"):
                    if edited_query:
                        research_state.current_query = edited_query
                        research_state.proposed_query = None
                        research_state.search_results = None # Reset for new search
                        research_state.pending_source_selection = False
                        st.session_state.messages.append({"role": "user", "content": f"Query approved: {edited_query}"})
                        st.rerun()
                    else:
                        st.warning("Cannot approve an empty query.")
            elif research_state.current_query:
                st.success(f"Query approved and active: {research_state.current_query}")
            else:
                st.info("No query proposed or active. Waiting for initial query generation or next step.")

            # --- Web Search Triggering (Interactive) ---
            if research_state.current_query and \
               not research_state.search_results and \
               not research_state.pending_source_selection:
                try:
                    st.session_state.messages.append({"role": "assistant", "content": f"Performing web search for: {research_state.current_query}"})
                    st.session_state.research_loop._web_search()
                    st.session_state.messages.append({"role": "assistant", "content": f"Web search completed. Found {len(research_state.search_results) if research_state.search_results else 0} results."})
                    st.rerun()
                except Exception as e:
                    st.error(f"Error during web search: {e}")
                    st.session_state.messages.append({"role": "assistant", "content": f"Error during web search: {e}"})

            # --- Search Results Display and Selection (Interactive) ---
            st.markdown("---")
            st.subheader("2. Source Selection")
            if research_state.pending_source_selection and research_state.search_results:
                st.info("Select sources from the search results below to include in the summary.")
                for i, result in enumerate(research_state.search_results):
                    checkbox_key = f"source_{result['link']}"
                    if checkbox_key not in st.session_state.selected_sources:
                         st.session_state.selected_sources[checkbox_key] = False
                    is_selected = st.checkbox(
                        f"{result['title']}",
                        key=checkbox_key,
                        value=st.session_state.selected_sources[checkbox_key],
                        on_change=lambda key=checkbox_key: st.session_state.selected_sources.update({key: st.session_state[key]})
                    )
                    st.caption(f"{result['link']}")
                    st.markdown(f"<small>{result['snippet']}</small>", unsafe_allow_html=True)
                    st.markdown("---")

                if st.button("Summarize Selected Sources", key="summarize_button"):
                    actual_selected_results = [res for res in research_state.search_results if st.session_state.selected_sources.get(f"source_{res['link']}", False)]
                    if actual_selected_results:
                        st.session_state.messages.append({"role": "user", "content": f"Summarizing {len(actual_selected_results)} selected sources..."})
                        try:
                            st.session_state.research_loop._summarize_sources(selected_results=actual_selected_results)
                            st.session_state.messages.append({"role": "assistant", "content": "Summarization complete."})
                        except Exception as e:
                            st.error(f"Error during summarization: {e}")
                            st.session_state.messages.append({"role": "assistant", "content": f"Error during summarization: {e}"})
                    else:
                        st.warning("No sources selected. Click checkboxes to select.")
                        st.session_state.messages.append({"role": "assistant", "content": "No sources were selected. Please select at least one source."})
                    st.session_state.selected_sources = {} # Clear selections
                    st.rerun()
            elif research_state.search_results and not research_state.pending_source_selection:
                 st.success("Sources processed. Ready for next step or reflection.")
        elif research_state.final_report: # For completed non-interactive runs
            st.markdown("---")
            st.info("Research was run in automated mode. Interactive steps like query approval and source selection were bypassed.")


        # --- Summary Display (Common for both modes) ---
        st.markdown("---")
        st.subheader("3. Research Summaries")
        if research_state.final_report: # If final report exists, show it primarily
            with st.expander("View Final Research Report", expanded=True):
                st.markdown(research_state.final_report)
        else: # Otherwise, show ongoing summary information
            if research_state.new_information:
                st.markdown("#### Latest Findings:")
                st.info(research_state.new_information)
            if research_state.accumulated_summary:
                with st.expander("View Accumulated Research Summary"):
                    st.markdown(research_state.accumulated_summary)
            else:
                st.info("No summary available yet.")

        st.markdown("---")
        st.subheader("4. Knowledge Graph")
        if research_state and research_state.knowledge_graph_nodes: # Check if nodes exist
            nodes = []
            edges = []
            for node_data in research_state.knowledge_graph_nodes:
                nodes.append(Node(id=node_data['id'],
                                  label=node_data['label'],
                                  shape="box",
                                  color="lightblue"
                                 ))
            if research_state.knowledge_graph_edges: # Edges might be empty
                for edge_data in research_state.knowledge_graph_edges:
                    edges.append(Edge(source=edge_data['source'],
                                      target=edge_data['target'],
                                      label=edge_data.get('label', ''),
                                      color="gray"
                                     ))

            if nodes: # Only proceed if there are nodes
                agraph_config = Config(
                    width=750, height=600, directed=True, physics=True, hierarchical=False,
                    # **kwargs
                )
                # config = config_builder.build() # This line caused the error
                try:
                    agraph(nodes=nodes, edges=edges, config=agraph_config) # Display graph, ignore return value for now
                except Exception as e:
                    st.error(f"Error rendering knowledge graph: {e}")
            else: # No nodes to display
                st.info("No knowledge graph data to display. Nodes list is empty.")
        elif research_state: # research_state exists but no KG nodes
             st.info("Knowledge graph will appear here after information extraction. No graph data generated yet.")
        # else: # research_state itself is None, already handled by outer if/else for "Start research..."

    else: # st.session_state.research_state is None
        st.info("Enter a research topic and click 'Start Research' to begin.")

if __name__ == "__main__":
    # To run streamlit, you'd typically use `streamlit run deep_research_project/streamlit_app.py`
    # This main guard is here for completeness but direct execution might need path adjustments
    # depending on how it's run. For development, use the CLI command.
    main()
