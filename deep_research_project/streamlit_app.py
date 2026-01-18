import streamlit as st
import sys
import os
import datetime
import asyncio
import logging
import traceback

# Adjust path to import from sibling directories
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from deep_research_project.config.config import Configuration
from deep_research_project.core.state import ResearchState
from deep_research_project.core.research_loop import ResearchLoop
from streamlit_agraph import agraph, Node, Edge, Config
from typing import Callable, Optional

logger = logging.getLogger(__name__)

def format_follow_up_log_for_download(follow_up_log: list) -> str:
    if not follow_up_log: return "No follow-up Q&A recorded."
    formatted_log = ["# Follow-up Q&A Log\n"]
    for i, qa in enumerate(follow_up_log):
        formatted_log.append(f"## Question {i+1}: {qa.get('question', 'N/A')}\n")
        formatted_log.append(f"**Answer:**\n{qa.get('answer', 'N/A')}\n---\n")
    return "\n".join(formatted_log)

def format_combined_download_data(final_report: Optional[str], follow_up_log: list) -> str:
    report = final_report if final_report else "No report generated."
    return f"{report}\n\n---\n\n{format_follow_up_log_for_download(follow_up_log)}"

def main():
    st.set_page_config(layout="wide", page_title="Modern Research Assistant")
    st.title("Modern Research Assistant (Async)")

    if "messages" not in st.session_state: st.session_state.messages = []
    if "selected_sources" not in st.session_state: st.session_state.selected_sources = {}

    with st.sidebar:
        st.header("Controls")
        interactive = st.toggle("Run Interactively?", value=False)
        snippets_only = st.toggle("Use Snippets Only?", value=False)
        max_chars = st.number_input("Max Chars/Source (0=unlim)", min_value=0, value=10000, step=1000)
        process_pdf = st.toggle("Process PDF Files?", value=True)

        topic = st.text_input("Research Topic:")

        if st.button("Start Research"):
            if topic:
                config = Configuration()
                config.INTERACTIVE_MODE = interactive
                config.USE_SNIPPETS_ONLY_MODE = snippets_only
                config.MAX_TEXT_LENGTH_PER_SOURCE_CHARS = max_chars
                config.PROCESS_PDF_FILES = process_pdf

                st.session_state.research_state = ResearchState(research_topic=topic)
                st.session_state.research_loop = ResearchLoop(config, st.session_state.research_state)

                if not config.INTERACTIVE_MODE:
                    with st.status("Automated research processing...") as status:
                        asyncio.run(st.session_state.research_loop.run_loop())
                        status.update(label="Complete!", state="complete")
                    st.rerun()
                else:
                    st.info("Generating plan...")
                    asyncio.run(st.session_state.research_loop._generate_research_plan())
                    st.rerun()

    if "research_state" in st.session_state:
        state = st.session_state.research_state
        loop = st.session_state.research_loop

        st.subheader(f"Topic: {state.research_topic}")

        # Progress UI
        if state.research_plan:
            st.markdown("**Research Progress:**")
            cols = st.columns(len(state.research_plan))
            for i, section in enumerate(state.research_plan):
                with cols[i]:
                    icon = "✅" if section['status'] == 'completed' else "⏳" if section['status'] == 'researching' else "⚪"
                    st.markdown(f"{icon} {section['title']}")

        # Interactive Plan Approval
        if loop.interactive_mode and state.research_plan and not state.plan_approved:
            st.divider()
            st.subheader("Plan Approval")
            for i, sec in enumerate(state.research_plan):
                with st.expander(f"Section {i+1}: {sec['title']}", expanded=True):
                    state.research_plan[i]['title'] = st.text_input(f"Title {i}", value=sec['title'], key=f"t_{i}")
                    state.research_plan[i]['description'] = st.text_area(f"Desc {i}", value=sec['description'], key=f"d_{i}")
            if st.button("Approve & Start"):
                state.plan_approved = True
                asyncio.run(loop.run_loop())
                st.rerun()
            return

        # Interactive Query Approval
        if loop.interactive_mode and state.proposed_query and not state.current_query:
            st.divider()
            st.subheader("Query Approval")
            q = st.text_input("Review Query:", value=state.proposed_query)
            if st.button("Search with this Query"):
                state.current_query = q
                state.proposed_query = None
                asyncio.run(loop.run_loop())
                st.rerun()

        # Interactive Source Selection
        if loop.interactive_mode and state.pending_source_selection and state.search_results:
            st.divider()
            st.subheader("Select Sources")
            selected = []
            for res in state.search_results:
                if st.checkbox(res['title'], key=f"src_{res['link']}"):
                    selected.append(res)
            if st.button("Summarize Selected"):
                asyncio.run(loop._summarize_sources(selected))
                asyncio.run(loop.run_loop())
                st.rerun()

        # Results Display
        if state.final_report:
            st.success("Final Report Generated")
            with st.expander("View Report", expanded=True):
                st.markdown(state.final_report)

            # Follow-up
            st.divider()
            st.subheader("Follow-up Questions")
            for qa in state.follow_up_log:
                with st.chat_message("user"): st.write(qa['question'])
                with st.chat_message("assistant"): st.write(qa['answer'])

            fq = st.chat_input("Ask a follow-up question...")
            if fq:
                state.follow_up_log.append({"question": fq, "answer": "Thinking..."})
                # Re-run logic for follow-up
                prompt = loop.format_follow_up_prompt(state.final_report, fq)
                ans = asyncio.run(loop.llm_client.generate_text(prompt))
                state.follow_up_log[-1]["answer"] = ans
                st.rerun()
        else:
            if state.new_information:
                st.info("Latest Findings:")
                st.write(state.new_information)

if __name__ == "__main__":
    main()
