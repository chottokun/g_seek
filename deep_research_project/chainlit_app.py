import chainlit as cl
import os
import sys
import asyncio
import logging

# Adjust path to import from sibling directories
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from deep_research_project.config.config import Configuration
from deep_research_project.core.state import ResearchState
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

@cl.on_message
async def main(message: cl.Message):
    config = cl.user_session.get("config")
    topic = message.content

    state = ResearchState(research_topic=topic)
    cl.user_session.set("state", state)

    # Add a stop button
    actions = [
        cl.Action(name="stop_research", value="stop", label="⏹️ Stop Research", description="Interrupt the research process")
    ]

    root_msg = cl.Message(content=f"## Researching: {topic}", actions=actions)
    await root_msg.send()

    # Progress reporting using Chainlit steps
    current_step = None

    async def progress_callback(info: str):
        nonlocal current_step
        if current_step:
            await current_step.update(content=info)
            # If the info seems like a new major task, we might want a new step,
            # but for now let's just update the current one or create a new one if none exists.

        # Create a new step for major transitions
        if "Starting" in info or "Generating" in info or "Synthesizing" in info or "Searching" in info:
            current_step = cl.Step(name="Research Task", parent_id=root_msg.id)
            await current_step.send()
            current_step.content = info
            await current_step.update()
        else:
            if not current_step:
                current_step = cl.Step(name="Research Task", parent_id=root_msg.id)
                await current_step.send()
            current_step.content = info
            await current_step.update()

    loop = ResearchLoop(config, state, progress_callback=progress_callback)

    try:
        # Run the research loop in the background or just await it?
        # Awaiting it is fine as long as we can still process actions.
        final_report = await loop.run_loop()

        if state.is_interrupted:
            await cl.Message(content="⚠️ Research was interrupted. Generating partial report...").send()
        else:
            await cl.Message(content="✅ Research complete!").send()

        if final_report:
            # Send the final report as a new message
            await cl.Message(content=final_report).send()

            # Offer download
            report_path = "research_report.md"
            with open(report_path, "w", encoding="utf-8") as f:
                f.write(final_report)

            elements = [
                cl.File(name="research_report.md", path=report_path, display="inline")
            ]
            await cl.Message(content="You can download the report below:", elements=elements).send()

    except Exception as e:
        logger.error(f"Error in research loop: {e}", exc_info=True)
        await cl.Message(content=f"❌ An error occurred: {str(e)}").send()

@cl.action_callback("stop_research")
async def on_action(action: cl.Action):
    state = cl.user_session.get("state")
    if state:
        state.is_interrupted = True
        await cl.Message(content="Stopping research... please wait for the current task to finish.").send()
        await action.remove()
