import chainlit as cl
import os
import sys
import asyncio
import logging
import uuid
import time
import shutil
import pathlib
import json
from typing import List
from pyvis.network import Network

# Adjust path to import from sibling directories
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from deep_research_project.config.config import Configuration
from deep_research_project.core.state import ResearchState, SearchResult
from deep_research_project.core.research_loop import ResearchLoop
from chainlit.input_widget import Switch, Slider, Select

logger = logging.getLogger(__name__)

def cleanup_old_reports(report_dir: pathlib.Path, cleanup_age: int):
    """Deletes files in report_dir older than cleanup_age."""
    if not report_dir.exists():
        return
    
    # Safety check: ensure report_dir is within the project root and is not the root itself
    try:
        project_root = pathlib.Path(__file__).parent.parent.resolve()
        resolved_report_dir = report_dir.resolve()

        if not resolved_report_dir.is_relative_to(project_root) or resolved_report_dir == project_root:
            logger.warning(f"Cleanup skipped: {report_dir} is not a valid subdirectory of {project_root}")
            return
    except Exception as e:
        logger.error(f"Error validating report directory: {e}")
        return

    now = time.time()
    count = 0
    try:
        for item in report_dir.iterdir():
            if item.is_file():
                if now - item.stat().st_mtime > cleanup_age:
                    item.unlink()
                    count += 1
            elif item.is_dir():
                # If we used unique subdirs, clean them too
                if now - item.stat().st_mtime > cleanup_age:
                    shutil.rmtree(item)
                    count += 1
        if count > 0:
            logger.info(f"Cleaned up {count} old report files/directories.")
    except Exception as e:
        logger.error(f"Error during report cleanup: {e}")

@cl.on_chat_start
async def start():
    try:
        config = Configuration()
        # Run cleanup occasionally on startup
        cleanup_old_reports(pathlib.Path(config.REPORT_DIR), config.CLEANUP_AGE_SECONDS)
        
        cl.user_session.set("config", config)

        await cl.ChatSettings([
            Select(id="language", label="Language", values=["Japanese", "English"], initial_value=config.DEFAULT_LANGUAGE),
            Select(id="search_api", label="Search Engine", values=["duckduckgo", "searxng", "tavily"], initial_value=config.SEARCH_API),
            Switch(id="interactive_mode", label="Interactive Mode", initial=config.INTERACTIVE_MODE),
            Slider(id="max_loops", label="Max Research Loops", initial=config.MAX_RESEARCH_LOOPS, min=1, max=10, step=1),
            Switch(id="snippets_only", label="Use Snippets Only", initial=config.USE_SNIPPETS_ONLY_MODE),
            Slider(id="max_search_results", label="Max Search Results", initial=config.MAX_SEARCH_RESULTS_PER_QUERY, min=1, max=10, step=1),
            Slider(id="chunk_size", label="Summarization Chunk Size (Chars)", initial=config.SUMMARIZATION_CHUNK_SIZE_CHARS, min=500, max=30000, step=500),
            Slider(id="chunk_overlap", label="Summarization Chunk Overlap (Chars)", initial=config.SUMMARIZATION_CHUNK_OVERLAP_CHARS, min=0, max=5000, step=100),
            Slider(id="max_concurrent_chunks", label="Max Concurrent Chunks", initial=config.MAX_CONCURRENT_CHUNKS, min=1, max=10, step=1),
            Slider(id="llm_rpm", label="LLM Rate Limit (RPM)", initial=config.LLM_RATE_LIMIT_RPM, min=1, max=120, step=10),
        ]).send()

        await cl.Message(content="""# Deep Research Assistant
AIを活用したリサーチを開始します。
リサーチしたいトピックを入力してください。

※ 左側の設定（Chat Settings）から、**言語**や**自動・対話モード**の切り替えが可能です。""").send()
    except Exception as e:
        await cl.Message(content=f"Error initializing configuration: {e}").send()

@cl.on_settings_update
async def setup_agent(settings):
    config = cl.user_session.get("config")
    state = cl.user_session.get("state")
    loop = cl.user_session.get("loop")

    if config:
        cl.user_session.set("language", settings["language"])
        config.SEARCH_API = settings["search_api"]
        config.INTERACTIVE_MODE = settings["interactive_mode"]
        config.MAX_RESEARCH_LOOPS = int(settings["max_loops"])
        config.USE_SNIPPETS_ONLY_MODE = settings["snippets_only"]
        config.MAX_SEARCH_RESULTS_PER_QUERY = int(settings["max_search_results"])

        chunk_size = int(settings["chunk_size"])
        chunk_overlap = int(settings["chunk_overlap"])

        # Simple validation to prevent app crash
        if chunk_overlap >= chunk_size:
            chunk_overlap = chunk_size - 1
            await cl.Message(content=f"⚠️ Chunk overlap was adjusted to {chunk_overlap} because it must be less than chunk size.").send()

        config.SUMMARIZATION_CHUNK_SIZE_CHARS = chunk_size
        config.SUMMARIZATION_CHUNK_OVERLAP_CHARS = chunk_overlap

        # Optimizations
        config.MAX_CONCURRENT_CHUNKS = int(settings["max_concurrent_chunks"])
        config.LLM_RATE_LIMIT_RPM = int(settings["llm_rpm"])

        if state:
            state.language = settings["language"]
        if loop:
            loop.interactive_mode = settings["interactive_mode"]

        logger.info(f"Settings updated: {settings}")

async def handle_interactive_steps(loop: ResearchLoop, state: ResearchState):
    """Handles interactive steps if enabled."""
    if not loop.interactive_mode:
        return await loop.run_loop()

    while not state.final_report and not state.is_interrupted:
        res = await loop.run_loop()
        if state.final_report or state.is_interrupted:
            return res

        # Check what kind of interaction is needed
        auto_action = cl.Action(name="switch_to_auto", payload={"value": "auto"}, label="⚡ Switch to Automatic", description="Continue automatically from here")

        if not state.plan_approved and state.research_plan:
            # Plan Approval
            plan_text = "### Proposed Research Plan\n"
            for i, sec in enumerate(state.research_plan):
                plan_text += f"{i+1}. **{sec['title']}**: {sec['description']}\n"

            actions = [
                cl.Action(name="approve_plan", payload={"value": "approve"}, label="✅ Approve & Start"),
                auto_action
            ]
            await cl.Message(content=plan_text, actions=actions).send()
            return # Wait for action callback

        if state.proposed_query and not state.current_query:
            # Query Approval
            actions = [
                cl.Action(name="approve_query", payload={"value": "approve"}, label=f"🔍 Search: {state.proposed_query}"),
                auto_action
            ]
            await cl.Message(content=f"Next research step: **{state.proposed_query}**", actions=actions).send()
            return

        if state.pending_source_selection and state.search_results:
            # Source Selection
            content = "### Select sources to summarize:\n"
            actions = []
            for i, res in enumerate(state.search_results):
                content += f"{i+1}. [{res['title']}]({res['link']})\n"
                actions.append(cl.Action(name="select_source", payload={"value": str(i)}, label=f"Source {i+1}"))

            actions.append(cl.Action(name="summarize_all", payload={"value": "all"}, label="All Sources"))
            actions.append(cl.Action(name="summarize_selected", payload={"value": "done"}, label="完了 (Done Selecting)"))
            actions.append(auto_action)

            cl.user_session.set("selected_indices", [])
            await cl.Message(content=content, actions=actions).send()
            return

    return state.final_report

@cl.on_message
async def main(message: cl.Message):
    config = cl.user_session.get("config")
    state = cl.user_session.get("state")

    if state and state.final_report:
        # Follow-up question
        loop = cl.user_session.get("loop")
        async with cl.Step(name="Thinking"):
            prompt = loop.format_follow_up_prompt(state.final_report, message.content)
            answer = await loop.llm_client.generate_text(prompt)

        state.follow_up_log.append({"question": message.content, "answer": answer})
        await cl.Message(content=answer).send()
        return

    # Start new research
    topic = message.content
    language = cl.user_session.get("language") or config.DEFAULT_LANGUAGE
    state = ResearchState(research_topic=topic, language=language)
    cl.user_session.set("state", state)

    actions = [
        cl.Action(name="stop_research", payload={"value": "stop"}, label="⏹️ Stop Research")
    ]
    root_msg = cl.Message(content=f"## Researching: {topic}", actions=actions)
    await root_msg.send()

    progress_messages = []  # Track progress as messages

    async def progress_callback(info: str):
        """Simple message-based progress display"""
        # Send each progress update as a visible message
        await cl.Message(content=f"📍 {info}", author="Progress").send()

    loop = ResearchLoop(config, state, progress_callback=progress_callback)
    cl.user_session.set("loop", loop)

    try:
        final_report = await handle_interactive_steps(loop, state)
        if final_report:
            await display_final_report(final_report, state)
    except Exception as e:
        logger.error(f"Error in research loop: {e}", exc_info=True)
        await cl.Message(content=f"❌ An error occurred: {str(e)}").send()

async def display_final_report(final_report: str, state: ResearchState):
    config = cl.user_session.get("config")
    report_dir = pathlib.Path(config.REPORT_DIR) if config else pathlib.Path("temp_reports")

    if state.is_interrupted:
        await cl.Message(content="⚠️ Research was interrupted. Generating partial report...").send()
    else:
        await cl.Message(content="✅ Research complete!").send()

    await cl.Message(content=final_report).send()

    # Thread-safe unique report path
    try:
        report_dir.mkdir(exist_ok=True)
        unique_id = uuid.uuid4().hex

        elements = []

        # Report file
        report_filename = f"research_report_{unique_id}.md"
        report_path = report_dir / report_filename
        with open(report_path, "w", encoding="utf-8") as f:
            f.write(final_report)
        elements.append(cl.File(name="research_report.md", path=str(report_path), display="inline"))

        # Knowledge Graph files
        if state.knowledge_graph_nodes:
            # JSON
            kg_json_filename = f"knowledge_graph_{unique_id}.json"
            kg_json_path = report_dir / kg_json_filename
            kg_data = {
                "nodes": state.knowledge_graph_nodes,
                "edges": state.knowledge_graph_edges
            }
            with open(kg_json_path, "w", encoding="utf-8") as f:
                json.dump(kg_data, f, indent=2, ensure_ascii=False)
            elements.append(cl.File(name="knowledge_graph.json", path=str(kg_json_path), display="inline"))

            # HTML (Visual)
            try:
                kg_html_filename = f"knowledge_graph_{unique_id}.html"
                kg_html_path = report_dir / kg_html_filename
                net = Network(height="600px", width="100%", notebook=False, directed=True)
                for node in state.knowledge_graph_nodes:
                    net.add_node(node['id'], label=node['label'], title=node['type'], group=node['type'])
                for edge in state.knowledge_graph_edges:
                    net.add_edge(edge['source'], edge['target'], label=edge['label'])
                net.save_graph(str(kg_html_path))
                elements.append(cl.File(name="knowledge_graph_visual.html", path=str(kg_html_path), display="inline"))
            except Exception as e:
                logger.error(f"Failed to generate KG visual: {e}")

        await cl.Message(content="You can download the results below:", elements=elements).send()
    except Exception as e:
        logger.error(f"Failed to save results: {e}")
        await cl.Message(content="Failed to save the result files locally, but you can see the report above.").send()

    await cl.Message(content="You can ask follow-up questions about the report above.").send()

@cl.action_callback("switch_to_auto")
async def on_switch_to_auto(action: cl.Action):
    state = cl.user_session.get("state")
    loop = cl.user_session.get("loop")

    if not state or not loop: return

    await cl.Message(content="⚡ Switching to automatic mode...").send()

    # Update loop and config
    loop.interactive_mode = False
    loop.config.INTERACTIVE_MODE = False

    # Automatically handle current interactive state
    if not state.plan_approved:
        state.plan_approved = True

    if state.proposed_query and not state.current_query:
        state.current_query = state.proposed_query
        state.proposed_query = None

    if state.pending_source_selection:
        await loop._summarize_sources(state.search_results or [])

    await action.remove()

    # Resume research
    final_report = await handle_interactive_steps(loop, state)
    if final_report:
        await display_final_report(final_report, state)

@cl.action_callback("stop_research")
async def on_stop(action: cl.Action):
    state = cl.user_session.get("state")
    if state:
        state.is_interrupted = True
        await cl.Message(content="Stopping research... finishing current task.").send()
        await action.remove()

@cl.action_callback("approve_plan")
async def on_approve_plan(action: cl.Action):
    state = cl.user_session.get("state")
    loop = cl.user_session.get("loop")
    state.plan_approved = True
    await cl.Message(content="Plan approved. Starting research...").send()
    final_report = await handle_interactive_steps(loop, state)
    if final_report:
        await display_final_report(final_report, state)

@cl.action_callback("approve_query")
async def on_approve_query(action: cl.Action):
    state = cl.user_session.get("state")
    loop = cl.user_session.get("loop")
    state.current_query = state.proposed_query
    state.proposed_query = None
    await action.remove()
    final_report = await handle_interactive_steps(loop, state)
    if final_report:
        await display_final_report(final_report, state)

@cl.action_callback("select_source")
async def on_select_source(action: cl.Action):
    selected = cl.user_session.get("selected_indices")
    idx = int(action.payload.get("value", 0))
    if idx not in selected:
        selected.append(idx)
        await cl.Message(content=f"Source {idx+1} selected.").send()
    cl.user_session.set("selected_indices", selected)

@cl.action_callback("summarize_all")
async def on_summarize_all(action: cl.Action):
    state = cl.user_session.get("state")
    loop = cl.user_session.get("loop")
    await action.remove()
    await loop._summarize_sources(state.search_results)
    final_report = await handle_interactive_steps(loop, state)
    if final_report:
        await display_final_report(final_report, state)

@cl.action_callback("summarize_selected")
async def on_summarize_selected(action: cl.Action):
    state = cl.user_session.get("state")
    loop = cl.user_session.get("loop")
    selected_indices = cl.user_session.get("selected_indices")
    selected_sources = [state.search_results[i] for i in selected_indices]
    await action.remove()
    await loop._summarize_sources(selected_sources)
    final_report = await handle_interactive_steps(loop, state)
    if final_report:
        await display_final_report(final_report, state)
