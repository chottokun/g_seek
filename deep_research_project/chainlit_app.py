import chainlit as cl
import os
import sys
import asyncio
import logging
from typing import List

# Adjust path to import from sibling directories
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from deep_research_project.config.config import Configuration
from deep_research_project.core.state import ResearchState, SearchResult
from deep_research_project.core.research_loop import ResearchLoop

logger = logging.getLogger(__name__)

@cl.on_chat_start
async def start():
    try:
        config = Configuration()
        cl.user_session.set("config", config)

        await cl.Message(content="""# Deep Research Assistant
AIを活用した高度なリサーチを自動で行います。
リサーチしたいトピックを入力してください。""").send()
    except Exception as e:
        await cl.Message(content=f"Error initializing configuration: {e}").send()

async def handle_interactive_steps(loop: ResearchLoop, state: ResearchState):
    """Handles interactive steps if enabled."""
    if not loop.interactive_mode:
        return await loop.run_loop()

    while not state.final_report and not state.is_interrupted:
        res = await loop.run_loop()
        if state.final_report or state.is_interrupted:
            return res

        # Check what kind of interaction is needed
        if not state.plan_approved and state.research_plan:
            # Plan Approval
            plan_text = "### Proposed Research Plan\n"
            for i, sec in enumerate(state.research_plan):
                plan_text += f"{i+1}. **{sec['title']}**: {sec['description']}\n"

            actions = [
                cl.Action(name="approve_plan", value="approve", label="✅ Approve & Start"),
                cl.Action(name="edit_plan", value="edit", label="📝 Edit Plan (In Sidebar)")
            ]
            await cl.Message(content=plan_text, actions=actions).send()
            return # Wait for action callback

        if state.proposed_query and not state.current_query:
            # Query Approval
            actions = [
                cl.Action(name="approve_query", value="approve", label=f"🔍 Search: {state.proposed_query}"),
                cl.Action(name="edit_query", value="edit", label="✏️ Edit Query")
            ]
            await cl.Message(content=f"Next research step: **{state.proposed_query}**", actions=actions).send()
            return

        if state.pending_source_selection and state.search_results:
            # Source Selection
            content = "### Select sources to summarize:\n"
            actions = []
            for i, res in enumerate(state.search_results):
                content += f"{i+1}. [{res['title']}]({res['link']})\n"
                actions.append(cl.Action(name="select_source", value=str(i), label=f"Source {i+1}"))

            actions.append(cl.Action(name="summarize_all", value="all", label="All Sources"))
            actions.append(cl.Action(name="summarize_selected", value="done", label="Done Selecting"))

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
    state = ResearchState(research_topic=topic)
    cl.user_session.set("state", state)

    actions = [
        cl.Action(name="stop_research", value="stop", label="⏹️ Stop Research")
    ]
    root_msg = cl.Message(content=f"## Researching: {topic}", actions=actions)
    await root_msg.send()

    current_step = None

    async def progress_callback(info: str):
        nonlocal current_step
        if "Starting" in info or "Generating" in info or "Synthesizing" in info or "Searching" in info:
            current_step = cl.Step(name="Research Task", parent_id=root_msg.id)
            await current_step.send()

        if current_step:
            current_step.content = info
            await current_step.update()

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
    if state.is_interrupted:
        await cl.Message(content="⚠️ Research was interrupted. Generating partial report...").send()
    else:
        await cl.Message(content="✅ Research complete!").send()

    await cl.Message(content=final_report).send()

    report_path = "research_report.md"
    with open(report_path, "w", encoding="utf-8") as f:
        f.write(final_report)

    elements = [cl.File(name="research_report.md", path=report_path, display="inline")]
    await cl.Message(content="You can download the report below:", elements=elements).send()
    await cl.Message(content="You can ask follow-up questions about the report above.").send()

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
    idx = int(action.value)
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
