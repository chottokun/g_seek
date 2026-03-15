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
import logging

logger = logging.getLogger(__name__)

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
    
    await cl.Message(content="# Deep Research Assistant\nAIを活用したリサーチを開始します。テーマを入力してください。\n").send()

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
                    sources_md = "\n".join([f"- [{getattr(s, 'title', 'Title')}]({getattr(s, 'link') or '#'})" if hasattr(s, 'title') else f"- [{s.get('title', 'Title')}]({s.get('link') or '#'})" for s in recent_sources]) if recent_sources else "None found."
                    
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
                        
            # End of Node loop
            
        # Graph Execution Finished
        final_state = graph.get_state(config_dict).values
        report = final_state.get("final_report")
        
        await cl.Message(content="📑 **リサーチ結果を統合し、最終レポートを作成中...**").send()
        
        if report:
            # 1. Processing and Guarding
            logger.info(f"DEBUG: Processing final report. Length: {len(report)}")
            
            import re
            import json
            import tempfile
            from pyvis.network import Network
            import logging

            json_pattern = r"```json\s*\n(.*?)\n?```"
            json_matches = re.findall(json_pattern, report, re.DOTALL)
            
            if not json_matches:
                raw_json_match = re.search(r"(\{\s*\"nodes\":.*?\})", report, re.DOTALL | re.IGNORECASE)
                if raw_json_match:
                    json_matches = [raw_json_match.group(1)]
            
            file_elements = []
            
            # --- Visual Summary Creation (Wrapped in total safety) ---
            for idx, json_str in enumerate(json_matches):
                try:
                    def try_repair_json(s):
                        if not s: return None
                        try:
                            return json.loads(s)
                        except json.JSONDecodeError:
                            last_brace = s.rfind('}')
                            if last_brace != -1:
                                try: return json.loads(s[:last_brace+1])
                                except: pass
                            return None

                    json_obj = try_repair_json(json_str)
                    if not json_obj or not isinstance(json_obj, dict): 
                        logger.warning(f"DEBUG: JSON match {idx} is not a valid object.")
                        continue

                    # ENHANCED SAFETY: Ensure edges exists to prevent Pydantic-like skip
                    if 'nodes' not in json_obj: 
                        logger.warning(f"DEBUG: JSON match {idx} is missing 'nodes'.")
                        continue
                    
                    net = Network(notebook=False, height="600px", width="100%", directed=True)
                    net.set_options('{"physics": {"enabled": true}}')
                    
                    node_count = 0
                    for node in json_obj.get('nodes', []):
                        if not node or not isinstance(node, dict) or 'id' not in node: continue
                        nid = str(node['id'])
                        label = str(node.get('label', nid))
                        color = "#ff9999" if node.get('type') == 'core' else "#99ccff"
                        title_html = f"<b>{label}</b>"
                        if node.get('description'): title_html += f"<br><br>{str(node['description'])}"
                        net.add_node(nid, label=label, color=color, shape="box", title=title_html)
                        node_count += 1
                        
                    edge_count = 0
                    for edge in json_obj.get('edges', []):
                        if not edge or not isinstance(edge, dict): continue
                        u, v = edge.get('from'), edge.get('to')
                        if u is not None and v is not None:
                            net.add_edge(str(u), str(v), color="#999999")
                            edge_count += 1
                    
                    if node_count > 0:
                        with tempfile.NamedTemporaryFile(suffix=".html", prefix=f"viz_{idx}_", delete=False) as tf:
                            tmp_path = tf.name
                        net.save_graph(tmp_path)
                        
                        file_elements.append(
                            cl.File(name=f"Visual_Summary_{idx+1}.html", path=tmp_path, display="side")
                        )
                        logger.info(f"DEBUG: Created Visual Summary {idx+1} with {node_count} nodes.")

                except Exception as e:
                    logger.error(f"CRITICAL: Failed to process Graph {idx}: {e}", exc_info=True)

            # --- Report File Creation ---
            try:
                with tempfile.NamedTemporaryFile(suffix=".md", prefix="report_", delete=False) as tf:
                    report_path = tf.name
                with open(report_path, "w", encoding="utf-8") as f:
                    f.write(report)
                
                file_elements.append(
                    cl.File(name="research_report.md", path=report_path, display="side")
                )
            except Exception as e:
                logger.error(f"DEBUG: Failed to create report file: {e}")

            # --- Final Messaging Flow (SPLIT TO PREVENT UI CRASH) ---
            
            # Step 1: Clean the text for chat display
            # The report is structured as: [Body] --- [Visual Summary] --- [Sources]
            # We want to show Body and Sources in chat, but remove the Visual Summary JSON.
            
            clean_report = report
            if "---" in report:
                parts = report.split("---")
                if len(parts) >= 3:
                    # parts[0] is body, parts[1] is visual summary, parts[2] is sources
                    body = parts[0].strip()
                    sources = parts[2].strip()
                    # Remove the header "## Sources" if we are adding it back clearly
                    clean_report = f"{body}\n\n---\n\n{sources}"
                elif len(parts) == 2:
                    # Only one separator? 
                    # If it has JSON, it's probably Body --- Visual Summary
                    if "```json" in parts[1]:
                        clean_report = parts[0].strip() + "\n\n*(リサーチが完了しました)*"
                    else:
                        clean_report = report # Keep as is
            
            # Final safety: remove any large JSON blocks from chat message
            clean_report = re.sub(r"```json.*?```", "\n*(詳細は添付の視覚的要約ファイルをご確認ください)*\n", clean_report, flags=re.DOTALL)
            clean_report = re.sub(r"##\s*Visual\s*Summary", "", clean_report, flags=re.IGNORECASE)
            
            clean_report = clean_report.strip()
            if not clean_report:
                clean_report = "リサーチが完了しました。詳細は添付のレポートファイルをご確認ください。"

            # Step 2: Send the text and files correctly
            # In latest Chainlit, we should send the message with elements.
            # Using display="side" in cl.File keeps them in the sidebar,
            # but we also want them prominently attached to the final report.
            
            await cl.Message(content=clean_report, elements=file_elements).send()
            logger.info(f"DEBUG: Sent final report with {len(file_elements)} attachments.")
            
            # Step 3: Clear session for next request
            cl.user_session.set("previous_context", report)
            cl.user_session.set("graph", None)
            logger.info("DEBUG: Research cycle finished and state reset.")

        else:
            logger.warning("DEBUG: Final report synthesis finished but 'final_report' is missing from state.")
            await cl.Message(content="⚠️ レポートの生成に失敗しました。以前のステップに問題があった可能性があります。").send()
            cl.user_session.set("graph", None)

    except Exception as e:
        import traceback
        err = traceback.format_exc()
        logger.error(f"FATAL ERROR in run_graph_and_render: {err}")
        try:
            await cl.Message(content=f"❌ **Error during execution:**\n```python\n{err}\n```").send()
        except: pass
        cl.user_session.set("graph", None)
