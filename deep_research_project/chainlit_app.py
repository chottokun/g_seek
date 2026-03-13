import chainlit as cl
import uuid
import os
import sys
import asyncio
import aiofiles

# Ensure we can import from core
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from deep_research_project.config.config import Configuration
from deep_research_project.core.graph import create_research_graph
from deep_research_project.tools.llm_client import LLMClient
from deep_research_project.tools.search_client import SearchClient
from deep_research_project.tools.content_retriever import ContentRetriever
from langgraph.checkpoint.memory import MemorySaver
from chainlit.input_widget import Select, Switch

@cl.on_chat_start
async def start():
    config = Configuration()
    cl.user_session.set("config", config)
    
    # Minimal UI Settings
    await cl.ChatSettings([
        Select(id="language", label="Language", values=["Japanese", "English"], initial_value=config.DEFAULT_LANGUAGE),
        Switch(id="interactive_mode", label="Interactive Mode (Plan Approval)", initial=config.INTERACTIVE_MODE),
        Switch(id="snippets_only", label="Snippet Only Mode (Fast)", initial=config.USE_SNIPPETS_ONLY_MODE),
    ]).send()
    
    await cl.Message(content="# Deep Research Assistant\nAIを活用したリサーチを開始します。テーマを入力してください。\n（※ 一から作り直したクリーンなUI実装です）").send()

@cl.on_settings_update
async def setup_agent(settings):
    config = cl.user_session.get("config")
    if config:
        cl.user_session.set("language", settings["language"])
        config.INTERACTIVE_MODE = settings["interactive_mode"]
        config.USE_SNIPPETS_ONLY_MODE = settings["snippets_only"]

@cl.on_message
async def main(message: cl.Message):
    config = cl.user_session.get("config")
    language = cl.user_session.get("language") or config.DEFAULT_LANGUAGE
    
    graph = cl.user_session.get("graph")
    thread_id = cl.user_session.get("thread_id")
    
    # 1. Initialize Graph for new request
    if not graph:
        memory = MemorySaver()
        llm = LLMClient(config)
        search = SearchClient(config)
        retriever = ContentRetriever(config)
        graph = create_research_graph(config, llm, search, retriever)
        
        thread_id = str(uuid.uuid4())
        cl.user_session.set("graph", graph)
        cl.user_session.set("thread_id", thread_id)
        
        # Include previous report context if following up
        prev_ctx = cl.user_session.get("previous_context", "")
        base_topic = message.content
        if prev_ctx:
            if language == "Japanese":
                topic_with_ctx = f"以下の前回の調査レポートを踏まえて、次の追加調査を行ってください。\n\n【追加調査の指示】\n{base_topic}\n\n【前回のレポート（参考）】\n{prev_ctx}"
            else:
                topic_with_ctx = f"Based on the previous research report below, please conduct the following follow-up research.\n\n[Follow-up Request]\n{base_topic}\n\n[Previous Report (Reference)]\n{prev_ctx}"
        else:
            topic_with_ctx = base_topic
            
        async def progress_cb(msg):
            await cl.Message(content=msg).send()
            
        initial_state = {
            "topic": topic_with_ctx,
            "language": language,
            "max_iterations": config.MAX_RESEARCH_LOOPS,
            "current_query": "",
            "iteration_count": 0,
            "findings": [],
            "sources": [],
            "research_plan": [],
            "current_section_index": 0,
            "plan_approved": not config.INTERACTIVE_MODE,
            "is_interrupted": False,
            "progress_callback": None # Keeping as None in State, passing real one via Config
        }
        config_dict = {
            "configurable": {
                "thread_id": thread_id,
                "progress_callback": progress_cb,
                "config": config
            }
        }
        
        await run_graph_and_render(graph, initial_state, config_dict, config)
        return

    # 2. Resume Interrupted Graph (e.g. Plan Approval)
    async def progress_cb(msg):
        await cl.Message(content=msg).send()
        
    config_dict = {
        "configurable": {
            "thread_id": thread_id,
            "progress_callback": progress_cb,
            "config": config
        }
    }
    state = graph.get_state(config_dict)
    
    if state and state.next:
        user_input = message.content.strip().lower()
        if user_input in ["y", "yes", "はい", "ok", "承認", "approve"]:
            try:
                graph.update_state(config_dict, {"plan_approved": True}, as_node="planner")
            except Exception:
                graph.update_state(config_dict, {"plan_approved": True})
            await cl.Message(content="✅ プランを承認しました。リサーチを開始します。").send()
            await run_graph_and_render(graph, None, config_dict, config)
        else:
            # Simple Plan Edit
            try:
                graph.update_state(config_dict, {
                    "plan_approved": True,
                    "plan": [{"title": "User Custom Plan", "description": message.content}]
                }, as_node="planner")
            except Exception:
                graph.update_state(config_dict, {
                    "plan_approved": True,
                    "plan": [{"title": "User Custom Plan", "description": message.content}]
                })
            await cl.Message(content="✏️ プランをカスタム内容に変更し、開始します。").send()
            await run_graph_and_render(graph, None, config_dict, config)
    else:
        # Start fresh if previous graph finished, but keep the previous report as context
        old_report = state.values.get("final_report", "") if state else ""
        if old_report:
            cl.user_session.set("previous_context", old_report)
        cl.user_session.set("graph", None)
        await main(message)

async def run_graph_and_render(graph, input_state, config_dict, config):
    try:
        current_step_msg = None
        async for event in graph.astream(input_state, config_dict):
            # Fetch the actual full state from the checkpointer to ensure lists like 'sources' are accumulated
            full_state = graph.get_state(config_dict).values
            
            for node, state_update in event.items():
                
                if node == "planner":
                    plan = full_state.get("plan", [])
                    plan_text = "### 📋 Proposed Research Plan\n"
                    for i, p in enumerate(plan):
                        plan_text += f"{i+1}. **{p['title']}**: {p['description']}\n"
                    
                    if config.INTERACTIVE_MODE and not full_state.get("plan_approved"):
                        plan_text += "\n\n⚠️ **Please review the plan.** Type `OK` or `承認` to start researching (Or type a custom plan to override)."
                    
                    await cl.Message(content=plan_text).send()

                elif node == "researcher":
                    query = state_update.get("current_query", full_state.get("current_query", "Unknown"))
                    idx = full_state.get("current_section_index", 0)
                    total = len(full_state.get("plan", []))
                    
                    # Get FULL accumulated sources
                    sources = full_state.get("sources", [])
                    recent_sources = sources[-5:] if len(sources) >= 5 else sources
                    sources_md = "\n".join([f"- [{getattr(s, 'title', 'Title')}]({getattr(s, 'link', '#')})" if hasattr(s, 'title') else f"- [{s.get('title', 'Title')}]({s.get('link', '#')})" for s in recent_sources]) if recent_sources else "None found."
                    
                    findings = full_state.get("findings", [])
                    recent_finding = findings[-1] if findings else "No findings."
                    safe_finding = (recent_finding[:200] + "...") if len(recent_finding) > 200 else recent_finding
                    
                    msg = f"### 🔍 Researching Section {idx+1}/{total}\n**Query:** `{query}`\n\n**Findings (Preview):**\n{safe_finding}\n\n**Recent Citations (Total: {len(sources)}):**\n{sources_md}"
                    
                    if not current_step_msg:
                        current_step_msg = cl.Message(content=msg)
                        await current_step_msg.send()
                    else:
                        current_step_msg.content = msg
                        await current_step_msg.update()
                        
                elif node == "reflector":
                    if current_step_msg:
                        msg = current_step_msg.content + "\n\n🧠 *Reflecting on findings...*"
                        current_step_msg.content = msg
                        await current_step_msg.update()
                        current_step_msg = None 
                    
                elif node == "skills_extractor":
                    new_skill = state_update.get("newly_extracted_skill")
                    if new_skill:
                        await cl.Message(content=f"💡 **New Domain Skill Extracted:** `{new_skill}`").send()
                        
            # Send final report if available
            if node == "final_reporter":
                await cl.Message(content="📝 *Synthesizing gathered information into the final research report...*").send()

        # Check if complete
        final_state = graph.get_state(config_dict).values
        if final_state.get("final_report"):
            report = final_state["final_report"]
            
            import re
            import json
            import tempfile
            from pyvis.network import Network
            import logging

            # 1. Extract JSON blocks and create temporary HTML files
            # More flexible pattern: allow the block to end with or without a final newline before the ```
            json_pattern = r"```json\s*\n(.*?)\n?```"
            json_matches = re.findall(json_pattern, report, re.DOTALL)
            
            # Fallback: if no code blocks, look for a raw JSON-like structure starting with "{" and ending with "}"
            if not json_matches:
                raw_json_match = re.search(r"(\{\s*\"nodes\":.*?\})", report, re.DOTALL | re.IGNORECASE)
                if raw_json_match:
                    json_matches = [raw_json_match.group(1)]
            
            file_elements = []
            
            for idx, json_str in enumerate(json_matches):
                try:
                    def try_repair_json(s):
                        try:
                            return json.loads(s)
                        except json.JSONDecodeError:
                            last_brace = s.rfind('}')
                            if last_brace != -1:
                                try: return json.loads(s[:last_brace+1])
                                except: pass
                            return None

                    json_obj = try_repair_json(json_str)
                    if not json_obj: continue

                    net = Network(notebook=False, height="600px", width="100%", directed=True)
                    # Options for a nicer look
                    net.set_options("""
                    var options = { "physics": { "barnesHut": { "gravitationalConstant": -3000, "centralGravity": 0.3, "springLength": 150 } } }
                    """)
                    
                    for node in json_obj.get('nodes', []):
                        color = "#ff9999" if node.get('type') == 'core' else "#99ccff"
                        title_html = f"<b>{node.get('label', str(node['id']))}</b>"
                        if 'description' in node and node['description']: title_html += f"<br><br>{node['description']}"
                        if 'url' in node and node['url']: title_html += f"<br><br><a href='{node['url']}' target='_blank'>[出典リンクを開く]</a>"
                        net.add_node(node['id'], label=node.get('label', str(node['id'])), color=color, shape="box", title=title_html)
                        
                    for edge in json_obj.get('edges', []):
                        net.add_edge(str(edge['from']), str(edge['to']), title=edge.get('label', ''), label=edge.get('label', ''))
                    
                    with tempfile.NamedTemporaryFile(suffix=".html", prefix=f"visual_summary_{idx}_", delete=False) as tf:
                        tmp_path = tf.name
                    await asyncio.to_thread(net.save_graph, tmp_path)
                    
                    file_elements.append(
                        cl.File(
                            name=f"Visual_Summary_{idx+1}.html",
                            path=tmp_path,
                            display="inline"
                        )
                    )
                except Exception as e:
                    logging.exception(f"Failed to process graph {idx}: {e}")

            # 2. Clean the report text
            # Remove JSON blocks for clean display
            clean_report = re.sub(json_pattern, "", report, flags=re.DOTALL)
            # Remove "## Visual Summary" or similar headers if they exist
            clean_report = re.sub(r"##\s*Visual\s*Summary.*?\n", "", clean_report, flags=re.IGNORECASE)
            clean_report = clean_report.strip()

            # 3. Create report file element
            try:
                with tempfile.NamedTemporaryFile(suffix=".md", prefix="research_report_", delete=False) as tf:
                    report_path = tf.name
                async with aiofiles.open(report_path, "w", encoding="utf-8") as f:
                    await f.write(report) # Save original full report including JSON
                
                file_elements.append(
                    cl.File(
                        name="research_report.md",
                        path=report_path,
                        display="inline"
                    )
                )
            except Exception as e:
                logging.exception(f"Failed to create report file: {e}")

            # 4. Send single consolidated message
            await cl.Message(content=clean_report, elements=file_elements).send()
            
    except Exception as e:
        import traceback
        err = traceback.format_exc()
        await cl.Message(content=f"❌ **Error during execution:**\n```python\n{err}\n```").send()
