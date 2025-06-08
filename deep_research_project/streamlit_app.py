import streamlit as st
import sys
import os

# Adjust path to import from sibling directories
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from deep_research_project.config.config import Configuration
from deep_research_project.core.state import ResearchState
from deep_research_project.core.research_loop import ResearchLoop
from streamlit_agraph import agraph, Node, Edge, Config
from typing import Callable, Optional # Added for progress_callback type hint
import logging # Added for logger
import traceback # Added for global exception traceback

logger = logging.getLogger(__name__) # Added logger

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
    if "max_text_length_chars" not in st.session_state:
        st.session_state.max_text_length_chars = 0 # Default to 0 (unlimited)
    if "process_pdf_files" not in st.session_state:
        st.session_state.process_pdf_files = True # Default UI state to True
    if "current_follow_up_question" not in st.session_state:
        st.session_state.current_follow_up_question = ""

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
        st.session_state.max_text_length_chars = st.number_input(
            "Max Chars/Source (0 for unlimited):",
            min_value=0,
            value=st.session_state.max_text_length_chars,
            step=1000,
            key="max_text_length_input",
            help="Maximum characters to process per web source. 0 means no limit. Truncation occurs before chunking."
        )
        st.session_state.process_pdf_files = st.toggle(
            "Process PDF Files?",
            value=st.session_state.process_pdf_files,
            key="process_pdfs_toggle",
            help="If ON, the system will attempt to download and extract text from PDF links. If OFF, PDF links will be skipped."
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
                    # Set MAX_TEXT_LENGTH_PER_SOURCE_CHARS based on Streamlit input
                    config.MAX_TEXT_LENGTH_PER_SOURCE_CHARS = st.session_state.max_text_length_chars
                    # Set PROCESS_PDF_FILES based on Streamlit toggle
                    config.PROCESS_PDF_FILES = st.session_state.process_pdf_files

                    st.session_state.research_state = ResearchState(research_topic=st.session_state.research_topic)
                    # Pass the modified config to ResearchLoop
                    # This initial ResearchLoop instance might be re-initialized later for non-interactive mode with callback
                    st.session_state.research_loop = ResearchLoop(config, st.session_state.research_state, progress_callback=None)

                    mode_message = "interactively" if config.INTERACTIVE_MODE else "non-interactively (automated)"
                    st.session_state.messages.append({"role": "assistant", "content": f"Research initialized to run {mode_message}."})

                    if config.USE_SNIPPETS_ONLY_MODE:
                        st.session_state.messages.append({"role": "assistant", "content": "Snippet-only mode is ON: Full content download will be skipped."})
                    else:
                        st.session_state.messages.append({"role": "assistant", "content": "Snippet-only mode is OFF: Attempting to download full content."})

                    if config.MAX_TEXT_LENGTH_PER_SOURCE_CHARS > 0:
                        st.session_state.messages.append({"role": "assistant", "content": f"Max text length per source set to: {config.MAX_TEXT_LENGTH_PER_SOURCE_CHARS} chars."})
                    else:
                        st.session_state.messages.append({"role": "assistant", "content": "Max text length per source: Unlimited."})

                    if config.PROCESS_PDF_FILES:
                        st.session_state.messages.append({"role": "assistant", "content": "PDF file processing is ON."})
                    else:
                        st.session_state.messages.append({"role": "assistant", "content": "PDF file processing is OFF."})

                    if not config.INTERACTIVE_MODE:
                        st.session_state.messages.append({"role": "assistant", "content": "Research running automatically..."}) # For sidebar

                        with st.status("Automated research processing...", expanded=True) as status_ui:
                            def streamlit_progress_updater(message: str):
                                status_ui.write(message) # Update the st.status box content

                            # Re-initialize ResearchLoop with the callback
                            st.session_state.research_loop = ResearchLoop(
                                config,
                                st.session_state.research_state,
                                progress_callback=streamlit_progress_updater
                            )

                            try:
                                st.session_state.research_loop.run_loop()
                                status_ui.update(label="Automated research complete!", state="complete", expanded=False)
                                st.session_state.messages.append({"role": "assistant", "content": "Automated research complete."}) # For sidebar
                            except Exception as e:
                                logger.error(f"Error during automated research run: {e}", exc_info=True)
                                st.error(f"An error occurred during the automated research: {e}")
                                status_ui.update(label="Research failed!", state="error", expanded=True)
                                st.session_state.messages.append({"role": "assistant", "content": f"Automated research failed: {e}"})

                        st.rerun() # Refresh UI to show final results/state
                    else:
                        # Interactive mode: Initialize ResearchLoop without progress_callback or it's handled differently
                        # For now, ensure it's initialized as it was before, if not already covered by the main init
                        if not st.session_state.research_loop or \
                           (st.session_state.research_loop and st.session_state.research_loop.progress_callback is not None):
                            # This re-init is to ensure no callback if it was set by a previous non-interactive run
                            st.session_state.research_loop = ResearchLoop(config, st.session_state.research_state, progress_callback=None)

                        st.session_state.messages.append({"role": "assistant", "content": "Generating initial query..."})
                        st.session_state.research_loop._generate_initial_query() # This will use the loop instance correctly set above
                        st.session_state.messages.append({"role": "assistant", "content": f"Initial query proposed: {st.session_state.research_state.proposed_query}"})
                        st.rerun()

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
        # logger.debug(f"Re-rendering. Current follow_up_log length: {len(research_state.follow_up_log) if research_state and hasattr(research_state, 'follow_up_log') else 'N/A'}") # Removed as per cleanup
        # logger.debug(f"Full research_state on rerender: {research_state}") # Removed as per cleanup / too verbose

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

        # --- Follow-up Q&A Section ---
        if research_state and (research_state.final_report or research_state.accumulated_summary):
            st.markdown("---")
            st.subheader("5. Follow-up Questions")

            if research_state.follow_up_log:
                for i, qa_pair in enumerate(research_state.follow_up_log):
                    try:
                        question_text = str(qa_pair.get('question', 'Error: Question not found'))
                        answer_text = str(qa_pair.get('answer', 'Error: Answer not found'))

                        with st.chat_message("user", avatar="❓"):
                            st.markdown(f"**Follow-up {i+1}:** {question_text}")
                        with st.chat_message("assistant", avatar="💡"):
                            st.markdown(answer_text)
                    except Exception as e_render:
                        logger.error(f"Error rendering follow-up Q&A entry #{i}: {qa_pair}. Error: {e_render}", exc_info=True)
                        st.error(f"Sorry, there was an error displaying follow-up entry #{i+1}. Please check the logs for details.")
                        # st.text(f"Problematic data: {qa_pair}") # Optionally uncomment for debugging
                    st.markdown("---")

            st.session_state.current_follow_up_question = st.text_input(
                "Ask a follow-up question based on the report/summary above:",
                value=st.session_state.current_follow_up_question,
                key="follow_up_input"
            )


            if st.button("Ask Follow-up", key="ask_follow_up_button"):
                try:
                    # print("DEBUG_streamlit_app: Top of 'Ask Follow-up' button try block (new_strategy_direct_llm_call).") # Removed

                    if st.session_state.current_follow_up_question and st.session_state.current_follow_up_question.strip() != "":
                        question = st.session_state.current_follow_up_question
                        # print(f"DEBUG_streamlit_app: Follow-up question: {question}") # Removed

                        # Get context from research_state
                        context_text = ""
                        if st.session_state.research_state:
                            if st.session_state.research_state.final_report and st.session_state.research_state.final_report.strip():
                                context_text = st.session_state.research_state.final_report
                            elif st.session_state.research_state.accumulated_summary and st.session_state.research_state.accumulated_summary.strip():
                                context_text = st.session_state.research_state.accumulated_summary

                        answer = "Error: Answer not set." # Initialize answer

                        if not context_text:
                            st.warning("No research context available to answer follow-up.")
                            answer = "I don't have enough context from the previous research to answer that."
                        elif not st.session_state.research_loop or not hasattr(st.session_state.research_loop, 'llm_client'):
                            st.error("LLM client not available in research_loop.")
                            answer = "LLM client not available to answer follow-up."
                        else:
                            # Format prompt using the (new/modified) method from ResearchLoop
                            follow_up_prompt = st.session_state.research_loop.format_follow_up_prompt(context_text, question)
                            # print(f"DEBUG_streamlit_app: Follow-up prompt constructed (first 100 chars): {follow_up_prompt[:100]}") # Removed

                            answer = "Error: LLM call for follow-up did not execute." # Default before try
                            try:
                                # print("DEBUG_streamlit_app: About to call llm_client.generate_text directly for follow-up.") # Removed
                                llm_client = st.session_state.research_loop.llm_client
                                answer = llm_client.generate_text(prompt=follow_up_prompt)
                                # print(f"DEBUG_streamlit_app: Direct call to llm_client.generate_text for follow-up completed. Answer snippet: {str(answer)[:100]}") # Removed
                                if not answer or str(answer).strip() == "":
                                    answer = "The LLM did not provide an answer to your follow-up question."
                                    st.info(answer) # Display in UI if LLM returns empty
                            except Exception as e_llm_call:
                                logger.error(f"Error during direct llm_client.generate_text for follow-up: {e_llm_call}", exc_info=True)
                                answer = f"Sorry, an error occurred while generating the answer: {e_llm_call}"
                                st.error(answer) # Display this error in UI

                        # All state updates and st.rerun() should be active now:
                        st.session_state.messages.append({"role": "user", "content": f"Follow-up Question: {question}"})
                        # st.session_state.messages.append({"role": "assistant", "content": f"Follow-up Answer: {str(answer)}" }) # Remove or comment out this line
                        if st.session_state.research_state:
                            if not hasattr(st.session_state.research_state, "follow_up_log") or \
                               st.session_state.research_state.follow_up_log is None or \
                               not isinstance(st.session_state.research_state.follow_up_log, list):
                                st.session_state.research_state.follow_up_log = []
                            st.session_state.research_state.follow_up_log.append({"question": question, "answer": str(answer)})

                        st.session_state.current_follow_up_question = ""

                        # Conditional rerun based on whether an error string was set for 'answer'
                        answer_str_for_check = str(answer)
                        if not (answer_str_for_check.startswith("Sorry, an error occurred") or \
                                answer_str_for_check.startswith("The LLM did not provide an answer") or \
                                answer_str_for_check.startswith("I don't have enough context") or \
                                answer_str_for_check.startswith("LLM client not available") or \
                                answer_str_for_check.startswith("Error:")) :
                            # print("DEBUG_streamlit_app: Follow-up successful, calling st.rerun().") # Removed
                            st.rerun()
                        # else: # No need to print if rerun is skipped, UI should show the error/warning
                            # print(f"DEBUG_streamlit_app: Follow-up had an issue or no answer, st.rerun() was skipped. Answer: {answer_str_for_check[:100]}") # Removed
                    else:
                        st.warning("Please enter a follow-up question.")
                        # print("DEBUG_streamlit_app: Follow-up question was empty.") # Removed

                    # print("DEBUG_streamlit_app: End of button handler (new_strategy_direct_llm_call).") # Removed

                except Exception as e_global_handler:
                    st.error(f"A critical error occurred in the follow-up button's operations: {e_global_handler}")
                    st.text("Detailed Traceback:")
                    st.text(traceback.format_exc()) # Make sure traceback is imported
                    logger.error(f"Global handler in 'Ask Follow-up' caught exception: {e_global_handler}", exc_info=True)
                    # print(f"DEBUG_streamlit_app: Global exception handler caught: {e_global_handler}") # Removed

    else: # st.session_state.research_state is None
        st.info("Enter a research topic and click 'Start Research' to begin.")

if __name__ == "__main__":
    # To run streamlit, you'd typically use `streamlit run deep_research_project/streamlit_app.py`
    # This main guard is here for completeness but direct execution might need path adjustments
    # depending on how it's run. For development, use the CLI command.
    main()
