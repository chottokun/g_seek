import chainlit as cl
import uuid
import os
import sys
import re
import json
import tempfile
import logging
import traceback
from pyvis.network import Network

# Ensure imports from parent directory
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from deep_research_project.config.config import Configuration
from deep_research_project.core.graph import create_research_graph
from deep_research_project.tools.llm_client import LLMClient
from deep_research_project.tools.search_client import SearchClient
from deep_research_project.tools.content_retriever import ContentRetriever
from langgraph.checkpoint.memory import MemorySaver
from chainlit.input_widget import Select, Switch

# Logger setup
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# --- Utility Functions ---

def clean_report_for_ui(report: str):
    """
    Bulletproof cleaning using RegEx to remove Visual Summary JSON blocks 
    without splitting the body prematurely.
    """
    if not report:
        return "リサーチが完了しました。レポートが空です。"
    
    # Remove any markdown JSON blocks containing "nodes" (Visual Summary)
    # This prevents '---' inside the report from breaking the display
    cleaned = re.sub(r'##\s*Visual\s*Summary.*?\n?```json.*?```', '', report, flags=re.DOTALL | re.IGNORECASE)
    
    # Remove large raw JSON blocks if they escaped the first regex
    cleaned = re.sub(r'```json\s*\{\s*"nodes":.*?\}\s*```', '', cleaned, flags=re.DOTALL)
    
    return cleaned.strip()

async def create_visual_summary(report: str):
    """
    Extracts the Visual Summary JSON and saves it as an HTML file.
    Returns a list of cl.File elements.
    """
    json_pattern = r"```json\s*\n(.*?)\n?```"
    json_matches = re.findall(json_pattern, report, re.DOTALL)
    
    # Fallback to loose search if no code block
    if not json_matches:
        raw_json_match = re.search(r"(\{\s*\"nodes\":.*?\})", report, re.DOTALL | re.IGNORECASE)
        if raw_json_match:
            json_matches = [raw_json_match.group(1)]
            
    elements = []
    for idx, json_str in enumerate(json_matches):
        try:
            # Basic validation
            if '"nodes"' not in json_str:
                continue
                
            json_obj = json.loads(json_str)
            if not isinstance(json_obj, dict) or 'nodes' not in json_obj:
                continue

            net = Network(notebook=False, height="600px", width="100%", directed=True)
            net.set_options('{"physics": {"enabled": true}}')
            
            node_count = 0
            for node in json_obj.get('nodes', []):
                if not node or 'id' not in node: continue
                nid = str(node['id'])
                label = str(node.get('label', nid))
                color = "#ff9999" if node.get('type') == 'core' else "#99ccff"
                title = node.get('description', '')
                net.add_node(nid, label=label, color=color, shape="box", title=title)
                node_count += 1
                
            for edge in json_obj.get('edges', []):
                if not edge: continue
                u, v = edge.get('from'), edge.get('to')
                if u is not None and v is not None:
                    net.add_edge(str(u), str(v), color="#999999")
            
            if node_count > 0:
                with tempfile.NamedTemporaryFile(suffix=".html", prefix=f"viz_{idx}_", delete=False) as tf:
                    tmp_path = tf.name
                net.save_graph(tmp_path)
                elements.append(cl.File(name=f"Network_Graph_{idx+1}.html", path=tmp_path, display="inline"))
                
        except Exception as e:
            logger.error(f"Visual Summary Error: {e}")
            
    return elements

# --- Chainlit Handlers ---

@cl.on_chat_start
async def start():
    config = Configuration()
    cl.user_session.set("config", config)
    
    await cl.ChatSettings([
        Select(id="language", label="Language", values=["Japanese", "English"], initial_value=config.DEFAULT_LANGUAGE),
        Switch(id="interactive_mode", label="Interactive Mode (Plan Approval)", initial=config.INTERACTIVE_MODE),
        Switch(id="snippets_only", label="Snippet Only Mode (Fast)", initial=config.USE_SNIPPETS_ONLY_MODE),
    ]).send()
    
    await cl.Message(content="# Deep Research v2 🚀\nより安定したリサーチ環境を構築しました。調査テーマを入力してください。").send()

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
    
    # 1. New Request Initialization
    if not graph:
        memory = MemorySaver()
        llm = LLMClient(config)
        search = SearchClient(config)
        retriever = ContentRetriever(config)
        graph = create_research_graph(config, llm, search, retriever)
        
        thread_id = str(uuid.uuid4())
        cl.user_session.set("graph", graph)
        cl.user_session.set("thread_id", thread_id)
        
        prev_report = cl.user_session.get("previous_context", "")
        topic = message.content
        if prev_report:
            topic = f"【前回の調査内容】\n{prev_report}\n\n【追加リクエスト】\n{topic}"
            
        initial_state = {
            "topic": topic,
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
        
        config_dict = {"configurable": {"thread_id": thread_id, "config": config}}
        await run_v2(graph, initial_state, config_dict)
        return

    # 2. Handle Plan Approval (Resume)
    config_dict = {"configurable": {"thread_id": thread_id, "config": config}}
    user_input = message.content.strip().lower()
    
    if user_input in ["y", "yes", "はい", "ok", "承認", "approve"]:
        graph.update_state(config_dict, {"plan_approved": True})
        await cl.Message(content="✅ プランを承認。リサーチを開始します...").send()
        await run_v2(graph, None, config_dict)
    else:
        # Custom plan override
        graph.update_state(config_dict, {
            "plan_approved": True,
            "plan": [{"title": "User Custom Plan", "description": message.content}]
        })
        await cl.Message(content="✏️ プランを独自内容に書き換えて開始します。").send()
        await run_v2(graph, None, config_dict)

async def run_v2(graph, input_state, config_dict):
    config = cl.user_session.get("config")
    try:
        current_step = None
        
        async for event in graph.astream(input_state, config_dict):
            # Inspect the state update
            node_name = list(event.keys())[0]
            full_state = graph.get_state(config_dict).values
            
            if node_name == "planner":
                plan = full_state.get("plan", [])
                plan_text = "### 📋 リサーチ計画案\n"
                for i, p in enumerate(plan):
                    plan_text += f"{i+1}. **{p['title']}**: {p['description']}\n"
                
                # Only show approval prompt if app is actually stopping for it
                is_interactive = config.INTERACTIVE_MODE
                if is_interactive and not full_state.get("plan_approved"):
                    plan_text += "\n\n⚠️ **上記プランで開始しますか？** \n承認する場合は `はい` または `OK` と返信してください。指示を送ることでプランを修正できます。"
                    await cl.Message(content=plan_text).send()
                else:
                    # Non-interactive or already approved, just show as a step
                    async with cl.Step(name="研究計画の確定") as step:
                        step.output = plan_text

            elif node_name == "researcher":
                query = full_state.get("current_query", "検索中...")
                idx = full_state.get("current_section_index", 0)
                plan = full_state.get("plan", [])
                total = len(plan)
                
                # Use Steps to keep the UI clean
                async with cl.Step(name=f"セクション {idx+1}/{total} の調査") as step:
                    step.output = f"🔍 クエリ: `{query}`"
            
            elif node_name == "final_reporter":
                await cl.Message(content="📑 **リサーチ完了。最終レポートを生成しました。**").send()

        # --- Report Generation & Delivery ---
        final_state = graph.get_state(config_dict).values
        report = final_state.get("final_report", "")
        
        if report:
            # 1. Clean for UI
            clean_md = clean_report_for_ui(report)
            
            # 2. Handle Large Report Truncation for Chat Window
            # Some browsers/UIs lag with 20k+ character markdown
            MAX_CHAR_LIMIT = 12000
            display_text = clean_md
            if len(clean_md) > MAX_CHAR_LIMIT:
                display_text = clean_md[:MAX_CHAR_LIMIT] + "\n\n---\n\n> ⚠️ **レポートが長大なため、チャット表示を省略しました。分析の全内容は、以下の添付ファイル（research_report.md）をダウンロードしてご確認ください。**"
            
            # 3. Create Attachments
            attachments = await create_visual_summary(report)
            
            # Add Main Report as File (Always side display for guaranteed download button)
            with tempfile.NamedTemporaryFile(suffix=".md", prefix="final_", delete=False) as tf:
                md_path = tf.name
            with open(md_path, "w", encoding="utf-8") as f:
                f.write(report)
            
            attachments.append(cl.File(name="research_report.md", path=md_path, display="side"))
            
            # 4. Final Delivery
            await cl.Message(content=display_text, elements=attachments).send()
            
            # Session maintenance
            cl.user_session.set("previous_context", report)
            cl.user_session.set("graph", None)
            logger.info(f"V2 Complete. Report length: {len(report)}")
        else:
            await cl.Message(content="⚠️ レポートの生成に失敗しました（データが空です）。").send()
            cl.user_session.set("graph", None)

    except Exception:
        err_msg = traceback.format_exc()
        logger.error(f"V2 Fatal: {err_msg}")
        await cl.Message(content=f"❌ **システムエラーが発生しました:**\n```python\n{err_msg}\n```").send()
        cl.user_session.set("graph", None)

if __name__ == "__main__":
    # Ensure this doesn't run via python command directly, but via chainlit
    pass
