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
import html
from typing import List
from pyvis.network import Network

# Adjust path to import from sibling directories
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from deep_research_project.config.config import Configuration
from deep_research_project.core.state import ResearchState, Source, SearchResult
from deep_research_project.core.research_loop import ResearchLoop
from deep_research_project.core.graph import create_research_graph
from deep_research_project.core.ki_distiller import KIDistiller
from deep_research_project.tools.llm_client import LLMClient
from deep_research_project.tools.search_client import SearchClient
from deep_research_project.tools.content_retriever import ContentRetriever
from chainlit.input_widget import Switch, Slider, Select, TextInput
from chainlit.action import Action as ClAction

logger = logging.getLogger(__name__)

def cleanup_old_reports(report_dir: pathlib.Path, cleanup_age: int):
    """Deletes files in report_dir older than cleanup_age."""
    if not report_dir.exists():
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
        config = cl.user_session.get("config")
        if not config:
            config = Configuration()
            cl.user_session.set("config", config)

        # Ensure current language is tracked separately for state initialization
        cl.user_session.set("language", config.DEFAULT_LANGUAGE)

        # Run cleanup occasionally on startup
        cleanup_old_reports(pathlib.Path(config.REPORT_DIR), config.CLEANUP_AGE_SECONDS)
        
        llm_providers = config.get_available_providers()
        await cl.ChatSettings([
            Select(id="language", label="Language", values=["Japanese", "English"], initial_value=config.DEFAULT_LANGUAGE),
            Select(id="llm_provider", label="LLM Provider", values=llm_providers, initial_value=config.LLM_PROVIDER if config.LLM_PROVIDER in llm_providers else llm_providers[0]),
            TextInput(id="llm_model", label="LLM Model", initial=config.LLM_MODEL),
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
        config.LLM_PROVIDER = settings["llm_provider"]
        config.LLM_MODEL = settings["llm_model"]
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
                content += f"{i+1}. [{res.title}]({res.link})\n"
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
    
    # Initialize clients and Graph
    llm_client = LLMClient(config)
    search_client = SearchClient(config)
    content_retriever = ContentRetriever(config)
    graph = create_research_graph(config, llm_client, search_client, content_retriever)
    
    # Use thread_id for persistence
    import uuid
    thread_id = str(uuid.uuid4())
    graph_config = {"configurable": {"thread_id": thread_id}}

    # Initial Agent State
    agent_state = {
        "topic": topic,
        "language": language,
        "plan": [],
        "current_section_index": -1,
        "findings": [],
        "sources": [],
        "knowledge_graph": {"nodes": [], "edges": []},
        "research_context": [],
        "activated_skill_ids": [],
        "is_complete": False,
        "iteration_count": 0,
        "max_iterations": config.MAX_RESEARCH_LOOPS * 2
    }

    try:
        # Run the graph and visualize nodes as cl.Steps
        # We use a loop to handle interrupts (Human-In-The-Loop)
        current_input = agent_state
        
        while True:
            async for event in graph.astream(current_input, config=graph_config, stream_mode="updates"):
                for node_name, node_update in event.items():
                    async with cl.Step(name=f"Node: {node_name.capitalize()}"):
                        if node_update:
                            if node_name == "planner":
                                plan_details = "\n".join([f"**{i+1}. {p['title']}**\n   {p.get('description', '')}" for i, p in enumerate(node_update.get('plan', []))])
                                await cl.Message(content=f"### 📋 Research Plan Generated\n{plan_details}").send()
                            elif node_name == "researcher":
                                # Show progress
                                sec_idx = agent_state.get('current_section_index', -1)
                                total_sec = len(agent_state.get('plan', []))
                                
                                # Show citations
                                sources = node_update.get("sources", [])
                                sources_md = "\n".join([f"- [{s.get('title', 'Link')}]({s.get('url', '#')})" for s in sources[-3:]]) if sources else "None found in this step."
                                
                                findings = node_update.get("findings", [])
                                summary = findings[-1] if findings else "No findings."
                                safe_summary = (summary[:200] + "...") if len(summary) > 200 else summary
                                
                                await cl.Message(content=f"### 🔍 Researching Section {sec_idx + 1} / {total_sec}\n**Gathered Info:** {safe_summary}\n\n**Citations:**\n{sources_md}").send()
                            elif node_name == "reflector":
                                await cl.Message(content="🧠 *Reflecting on findings and adjusting queries...*").send()
                            elif node_name == "skills_extractor":
                                await cl.Message(content="💡 *Extracted domain expertise for future use.*").send()
                        
                            # Update local agent_state Tracking
                            agent_state.update(node_update)

            # Check if we are interrupted (waiting for user input)
            state_snapshot = graph.get_state(graph_config)
            next_steps = state_snapshot.next
            
            # When using interrupt_after=["planner"], the next step is "researcher" and there are pending tasks
            if "researcher" in next_steps and not current_input:
                # Interrupted for Human-In-The-Loop Plan Approval
                plan_text = "\n".join([f"- {s['title']}: {s.get('description', '')}" for s in agent_state["plan"]])
                
                logger.info(f"Generating HITL actions. cl.Action type: {type(cl.Action)}")
                actions = [
                    cl.Action(name="approve", payload={"action": "approve"}, label="Proceed with Research"),
                    cl.Action(name="edit", payload={"action": "edit"}, label="Edit Plan"),
                    cl.Action(name="cancel", payload={"action": "cancel"}, label="Cancel Research")
                ]
                logger.info(f"Created actions: {actions}")
                
                res = await cl.AskActionMessage(
                    content=f"### Research Plan for Approval\n\n{plan_text}\n\nDo you want to proceed?",
                    actions=actions
                ).send()
                
                if res and (res.get("name") == "approve" or res.get("id") == "approve" or res.get("value") == "approve"):
                    current_input = None # Resume from checkpointer
                    continue
                elif res and (res.get("name") == "edit" or res.get("id") == "edit" or res.get("value") == "edit"):
                    # Simple text-based editing for prototype
                    new_plan_text = await cl.AskUserMessage(
                        content="Enter the new plan as a list of sections (Title: Description), one per line."
                    ).send()
                    
                    if new_plan_text:
                        # Parse and update state
                        new_plan = []
                        for line in new_plan_text['output'].split('\n'):
                            if ':' in line:
                                title, desc = line.split(':', 1)
                                new_plan.append({"title": title.strip("- ").strip(), "description": desc.strip()})
                        
                        if new_plan:
                            await graph.aupdate_state(graph_config, {"plan": new_plan})
                            await cl.Message(content="Plan updated. Resuming research...").send()
                            current_input = None 
                            continue
                else:
                    await cl.Message(content="Research cancelled by user.").send()
                    return
            else:
                # Graph finished normally
                break

        # Final Report Generation
        from deep_research_project.core.reporting import ResearchReporter
        reporter = ResearchReporter(llm_client)
        final_report = await reporter.finalize_report(topic, agent_state["plan"], language)
        
        # Knowledge Item Distillation
        knowledge_root = os.path.expanduser("~/.gemini/antigravity/knowledge")
        distiller = KIDistiller(llm_client, knowledge_root)
        ki_path = await distiller.distill_research(final_report, language)
        
        await cl.Message(content=f"### Knowledge Item Created\nInsight persisted at: `{ki_path}`").send()

        # Adapt for display
        class MockState:
            def __init__(self, agent_state, report):
                self.final_report = report
                self.knowledge_graph_nodes = agent_state["knowledge_graph"].get("nodes", [])
                self.knowledge_graph_edges = agent_state["knowledge_graph"].get("edges", [])
                self.is_interrupted = False
        
        await display_final_report(final_report, MockState(agent_state, final_report))

    except Exception as e:
        import traceback
        tb_str = traceback.format_exc()
        logger.error(f"Error in deep research graph: {e}\n{tb_str}")
        await cl.Message(content=f"❌ An error occurred during graph execution:\n```\n{tb_str}\n```").send()

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

        # Extract and render Mermaid diagram
        # Use plain text or a markdown snippet for now to prevent React crash
        import re
        mermaid_match = re.search(r'```mermaid\n(.*?)\n```', final_report, re.DOTALL)
        if mermaid_match:
            mermaid_code = mermaid_match.group(1)
            # Chainlit natively supports markdown. We just need to make sure the markdown was sent 
            # in the cl.Message content. The final_report is already sent as cl.Message(content=final_report).
            # If it's not rendering, we don't need a cl.Html hack that breaks the UI.
            pass

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
                
                # Color mapping for entity types
                type_colors = {
                    "Person": "#FF6B6B",
                    "Organization": "#4ECDC4",
                    "Concept": "#45B7D1",
                    "Event": "#FFA07A",
                    "Technology": "#98D8C8",
                    "Location": "#F0E68C"
                }
                
                for node in state.knowledge_graph_nodes:
                    # Enhanced properties display for hover (title)
                    # NOTE: Pyvis/vis.js does NOT render HTML in title tooltips, only plain text
                    props = node.get('properties', {})
                    mention_count = int(props.get('mention_count', 1))
                    node_size = 15 + min(mention_count * 5, 50) # Scale size by mention count
                    
                    # Security: Escape LLM-generated content
                    esc_label = html.escape(node['label'])
                    esc_type = html.escape(node['type'])

                    # Build plain text hover info (no HTML tags)
                    hover_info = f"{esc_label} ({esc_type})\n"
                    for k, v in props.items():
                        if k not in ['mention_count', 'section']:
                            hover_info += f"{html.escape(str(k))}: {html.escape(str(v))}\n"
                    
                    source_urls = node.get('source_urls', [])
                    esc_source_urls = [html.escape(str(url)) for url in source_urls]
                    if esc_source_urls:
                        hover_info += "\nSources:\n" + "\n".join([f"• {url}" for url in esc_source_urls])
                    
                    color = type_colors.get(node['type'], "#CCCCCC")
                    
                    # Dedicated property for the click handler to avoid regex extraction from title
                    # Security: Basic protocol validation
                    primary_url = source_urls[0] if source_urls else None
                    if primary_url and not primary_url.startswith(("http://", "https://")):
                        primary_url = None

                    net.add_node(
                        node['id'], 
                        label=esc_label,
                        title=hover_info, 
                        group=node['type'], 
                        color=color,
                        size=node_size,
                        source_url=primary_url
                    )
                    
                for edge in state.knowledge_graph_edges:
                    edge_props = edge.get('properties', {})
                    esc_edge_label = html.escape(edge['label'])
                    # Build plain text hover info (no HTML tags)
                    edge_hover = f"Relationship: {esc_edge_label}\n"
                    for k, v in edge_props.items():
                         edge_hover += f"{html.escape(str(k))}: {html.escape(str(v))}\n"
                    
                    net.add_edge(edge['source'], edge['target'], label=esc_edge_label, title=edge_hover)
                
                # Dynamic interaction: Click to open URL
                script = r"""
                var container = document.getElementById('mynetwork');
                network.on("click", function (params) {
                    if (params.nodes.length > 0) {
                        var nodeId = params.nodes[0];
                        var node = nodes.get(nodeId);
                        // Security: Use dedicated source_url property with protocol validation
                        if (node.source_url && (node.source_url.startsWith('http://') || node.source_url.startsWith('https://'))) {
                            window.open(node.source_url, '_blank');
                        }
                    }
                });
                """
                
                # We need to inject the script into the generated HTML. 
                # Pyvis doesn't support this directly via Network object easily for standalone HTML,
                # so we will append it to the saved file or use set_options.
                net.set_options("""
                var options = {
                  "interaction": {
                    "hover": true,
                    "navigationButtons": true
                  }
                }
                """)
                
                net.save_graph(str(kg_html_path))
                
                # Inject the click handler script into the saved HTML
                with open(kg_html_path, "r", encoding="utf-8") as f:
                    html_content = f.read()
                
                if "</body>" in html_content:
                    # Robust injection: Use rpartition to ensure we inject before the LAST </body> tag
                    parts = html_content.rpartition("</body>")
                    html_content = f"{parts[0]}<script>{script}</script></body>{parts[2]}"
                    with open(kg_html_path, "w", encoding="utf-8") as f:
                        f.write(html_content)

                elements.append(cl.File(name="knowledge_graph_visual.html", path=str(kg_html_path), display="inline"))
            except Exception as e:
                logger.error(f"Failed to generate KG visual: {e}")

        await cl.Message(content="You can download the results below:", elements=elements).send()
    except Exception as e:
        logger.error(f"Failed to save results: {e}")
        await cl.Message(content="Failed to save the result files locally, but you can see the report above.").send()

    new_res_action = cl.Action("new_research", {"value": "new"}, "🔄 New Research")
    await cl.Message(content="You can ask follow-up questions about the report above, or start a new research.", actions=[new_res_action]).send()

@cl.action_callback("new_research")
async def on_new_research(action: cl.Action):
    cl.user_session.set("state", None)
    cl.user_session.set("loop", None)
    await cl.Message(content="## New Research Started\nPlease enter your research topic.").send()
    await action.remove()

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
