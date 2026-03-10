import chainlit as cl
import uuid
import os
import sys

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
    
    # Minimal UI Settings to prevent overrides
    await cl.ChatSettings([
        Select(id="language", label="Language", values=["Japanese", "English"], initial_value=config.DEFAULT_LANGUAGE),
        Switch(id="interactive_mode", label="Interactive Mode (Plan Approval)", initial=config.INTERACTIVE_MODE),
    ]).send()
    
    await cl.Message(content="# Deep Research Assistant\nAIを活用したリサーチを開始します。テーマを入力してください。\n（※ 一から作り直したクリーンなUI実装です）").send()

@cl.on_settings_update
async def setup_agent(settings):
    config = cl.user_session.get("config")
    if config:
        cl.user_session.set("language", settings["language"])
        config.INTERACTIVE_MODE = settings["interactive_mode"]

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
            "is_interrupted": False
        }
        config_dict = {"configurable": {"thread_id": thread_id}}
        
        await run_graph_and_render(graph, initial_state, config_dict, config)
        return

    # 2. Resume Interrupted Graph (e.g. Plan Approval)
    config_dict = {"configurable": {"thread_id": thread_id}}
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
                        
                elif node == "final_reporter":
                    await cl.Message(content="📝 *Synthesizing gathered information into the final research report...*").send()

                        
        # Check if complete
        final_state = graph.get_state(config_dict).values
        if final_state.get("final_report"):
            report = final_state["final_report"]
            
            # Split the report to find JSON blocks and render them as Custom Elements
            import re
            # More permissive regex to catch ```json ... ``` with various spacers
            parts = re.split(r"(```json\s*\n.*?\n\s*```)", report, flags=re.DOTALL)
            
            for part in parts:
                if "```json" in part:
                    match = re.search(r"```json\s*\n(.*?)\n\s*```", part, re.DOTALL)
                    if match:
                        json_str = match.group(1).strip()
                        import logging
                        logging.info(f"VISUAL_SUMMARY_PAYLOAD: {json_str[:200]}...")
                        # Sent via VisualSummary component
                        msg = cl.Message(content="")
                        await msg.send()
                        try:
                            import json
                            import tempfile
                            from pyvis.network import Network
                            
                            def try_repair_json(s):
                                """Attempts to find the actual JSON object if there's trailing junk like '...'"""
                                try:
                                    return json.loads(s)
                                except json.JSONDecodeError:
                                    # Try to find the last '}' and cut there
                                    last_brace = s.rfind('}')
                                    if last_brace != -1:
                                        try:
                                            return json.loads(s[:last_brace+1])
                                        except: pass
                                    return None

                            json_obj = try_repair_json(json_str)
                            if not json_obj:
                                logging.warning("Failed to repair JSON for visual summary.")
                                continue

                            # Build the Interactive Graph using Pyvis
                            net = Network(notebook=False, height="600px", width="100%", directed=True)
                            net.set_options("""
                            var options = {
                              "physics": {
                                "barnesHut": {
                                  "gravitationalConstant": -3000,
                                  "centralGravity": 0.3,
                                  "springLength": 150
                                }
                              }
                            }
                            """)
                            
                            for node in json_obj.get('nodes', []):
                                color = "#ff9999" if node.get('type') == 'core' else "#99ccff"
                                
                                # 构建rich html tooltip (title)
                                title_html = f"<b>{node.get('label', str(node['id']))}</b>"
                                if 'description' in node and node['description']:
                                    title_html += f"<br><br>{node['description']}"
                                if 'url' in node and node['url']:
                                    title_html += f"<br><br><a href='{node['url']}' target='_blank'>[出典リンクを開く]</a>"
                                
                                net.add_node(
                                    node['id'], 
                                    label=node.get('label', str(node['id'])), 
                                    color=color, 
                                    shape="box",
                                    title=title_html
                                )
                                
                            for edge in json_obj.get('edges', []):
                                from_id = str(edge['from'])
                                to_id = str(edge['to'])
                                label = edge.get('label', '')
                                net.add_edge(from_id, to_id, title=label, label=label)
                                
                            # Save to temp file and send
                            tmp_path = tempfile.mktemp(suffix=".html", prefix="research_graph_")
                            net.save_graph(tmp_path)
                            
                            elements = [
                                cl.File(
                                    name="Interactive Visual Summary",
                                    path=tmp_path,
                                    mime="text/html",
                                    display="inline",
                                )
                            ]
                            await cl.Message(content="Visual summary generated as an interactive HTML diagram:", elements=elements).send()
                            
                        except Exception as e:
                            logging.error(f"Failed to parse or send Pyvis graph: {e}")
                            await cl.Message(content=f"Error parsing graph data: {e}").send()
                elif part.strip():
                    await cl.Message(content=part.strip()).send()
            
    except Exception as e:
        import traceback
        err = traceback.format_exc()
        await cl.Message(content=f"❌ **Error during execution:**\n```python\n{err}\n```").send()
