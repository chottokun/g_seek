import chainlit as cl
import uuid
import os
import sys
import re
import json
import tempfile
import logging
import traceback
import asyncio
from typing import Dict, Optional, List
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

# --- UI Helper Classes ---

class UIProgressManager:
    """Manages hierarchical progress updates using Chainlit Steps."""
    def __init__(self):
        self.section_steps: Dict[str, cl.Step] = {}
        self.main_step: Optional[cl.Step] = None

    async def handle_callback(self, msg: str):
        """Processes progress messages from the research core."""
        # Detect section-specific messages: "[Section Title] Detail message"
        match = re.match(r"\[(.*?)\] (.*)", msg)
        if match:
            section_title = match.group(1)
            details = match.group(2)
            
            if section_title not in self.section_steps:
                # Create a new step for this section
                step = cl.Step(name=f"🔍 {section_title}", parent_id=self.main_step.id if self.main_step else None)
                await step.send()
                self.section_steps[section_title] = step
            
            # Update the section step
            self.section_steps[section_title].output = details
            await self.section_steps[section_title].update()
        else:
            # General progress message
            if "Processing" in msg and "parallel" in msg:
                # Start of parallel processing
                self.main_step = cl.Step(name="🚀 リサーチ実行中 (並列処理)")
                await self.main_step.send()
            else:
                # Fallback to a simple message or update main step
                if self.main_step:
                    self.main_step.output = msg
                    await self.main_step.update()
                else:
                    await cl.Message(content=f"ℹ️ {msg}").send()

# --- Utility Functions ---

def robust_json_repair(json_str: str):
    """Attempts to repair common LLM JSON output issues."""
    json_str = json_str.strip()
    if not json_str: return None
    
    # Remove markdown code blocks if present
    json_str = re.sub(r'^```json\s*', '', json_str)
    json_str = re.sub(r'\s*```$', '', json_str)
    
    try:
        return json.loads(json_str)
    except json.JSONDecodeError:
        # Try to fix truncated JSON by adding missing closing braces
        for i in range(1, 10):
            try:
                return json.loads(json_str + '}' * i)
            except: continue
            
        # Try to find the last complete object
        last_brace = json_str.rfind('}')
        if last_brace != -1:
            try:
                return json.loads(json_str[:last_brace+1])
            except: pass
            
    return None

async def process_visual_summary(report: str):
    """Extracts Visual Summary JSON and creates network visualization."""
    # Find JSON blocks
    json_pattern = r"```json\s*\n(.*?)\n?```"
    json_matches = re.findall(json_pattern, report, re.DOTALL)
    
    if not json_matches:
        # Loose search for anything that looks like nodes/edges JSON
        raw_match = re.search(r"(\{.*\"nodes\".*\"edges\".*\})", report, re.DOTALL | re.IGNORECASE)
        if raw_match:
            json_matches = [raw_match.group(1)]
            
    elements = []
    for idx, json_str in enumerate(json_matches):
        data = robust_json_repair(json_str)
        if not data or 'nodes' not in data:
            continue
            
        try:
            net = Network(notebook=False, height="600px", width="100%", directed=True)
            # Use a nice template with localized labels if possible
            net.set_options("""
            var options = {
              "physics": {
                "forceAtlas2Based": { "gravitationalConstant": -50, "centralGravity": 0.01, "springLength": 100, "springConstant": 0.08 },
                "maxVelocity": 50, "solver": "forceAtlas2Based", "timestep": 0.35, "stabilization": { "iterations": 150 }
              }
            }
            """)
            
            for node in data.get('nodes', []):
                if 'id' not in node: continue
                nid = str(node['id'])
                label = str(node.get('label', nid))
                color = "#ff9999" if node.get('type') == 'core' else "#99ccff"
                desc = node.get('description', '')
                net.add_node(nid, label=label, color=color, shape="box", title=desc)
                
            for edge in data.get('edges', []):
                u, v = edge.get('from'), edge.get('to')
                if u is not None and v is not None:
                    net.add_edge(str(u), str(v), color="#999999", label=edge.get('label', ''))
            
            with tempfile.NamedTemporaryFile(suffix=".html", prefix=f"viz_{idx}_", delete=False) as tf:
                tmp_path = tf.name
            net.save_graph(tmp_path)
            elements.append(cl.File(name=f"Network_Graph_{idx+1}.html", path=tmp_path, display="side"))
            
        except Exception as e:
            logger.error(f"Visualization error: {e}")
            
    return elements

def clean_report_for_display(report: str):
    """Removes the large JSON blocks and internal technical sections from the chat display."""
    # Remove Visual Summary section completely from chat display
    report = re.sub(r'##\s*(?:Visual\s*Summary|視覚的要約).*?(?=##|---|$)', '', report, flags=re.DOTALL | re.IGNORECASE)
    # Remove any remaining raw JSON blocks
    report = re.sub(r'```json.*?```', '', report, flags=re.DOTALL)
    return report.strip()

# --- Chainlit Event Handlers ---

@cl.on_chat_start
async def start():
    config = Configuration()
    cl.user_session.set("config", config)
    
    await cl.ChatSettings([
        Select(id="language", label="Language", values=["Japanese", "English"], initial_value=config.DEFAULT_LANGUAGE),
        Switch(id="interactive_mode", label="Interactive Mode (Plan Approval)", initial=config.INTERACTIVE_MODE),
        Switch(id="snippets_only", label="Snippet Only Mode (Fast)", initial=config.USE_SNIPPETS_ONLY_MODE),
    ]).send()
    
    welcome_msg = (
        "# Deep Research Assistant v3 🔬\n\n"
        "AIを活用して深いリサーチを行い、構造化されたレポートを作成します。\n"
        "調査したいテーマを詳しく入力してください。"
    )
    await cl.Message(content=welcome_msg).send()

@cl.on_settings_update
async def setup_agent(settings):
    config = cl.user_session.get("config")
    if config:
        cl.user_session.set("language", settings["language"])
        config.INTERACTIVE_MODE = settings["interactive_mode"]
        config.USE_SNIPPETS_ONLY_MODE = settings["snippets_only"]
        await cl.Message(content=f"⚙️ 設定を更新しました: 言語={settings['language']}, 対話モード={settings['interactive_mode']}").send()

@cl.on_message
async def main(message: cl.Message):
    config = cl.user_session.get("config")
    language = cl.user_session.get("language") or config.DEFAULT_LANGUAGE
    
    graph = cl.user_session.get("graph")
    thread_id = cl.user_session.get("thread_id")
    
    # 1. New Research Session
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
            if language == "Japanese":
                topic = f"【前回の調査内容】\n{prev_report}\n\n【追加・詳細リクエスト】\n{topic}"
            else:
                topic = f"[Previous Report]\n{prev_report}\n\n[Follow-up Request]\n{topic}"
            
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
            "is_complete": False
        }
        
        ui_manager = UIProgressManager()
        cl.user_session.set("ui_manager", ui_manager)
        
        config_dict = {
            "configurable": {
                "thread_id": thread_id, 
                "config": config,
                "progress_callback": ui_manager.handle_callback
            }
        }
        
        await execute_research(graph, initial_state, config_dict)
        return

    # 2. Handle Plan Approval or Feedback
    config_dict = {
        "configurable": {
            "thread_id": thread_id, 
            "config": config,
            "progress_callback": cl.user_session.get("ui_manager").handle_callback
        }
    }
    
    user_input = message.content.strip().lower()
    if user_input in ["y", "yes", "はい", "ok", "承認", "approve"]:
        graph.update_state(config_dict, {"plan_approved": True})
        await cl.Message(content="✅ プランを承認しました。詳細リサーチを開始します。").send()
        await execute_research(graph, None, config_dict)
    else:
        # Custom plan override
        graph.update_state(config_dict, {
            "plan_approved": True,
            "plan": [{"title": "User Custom Plan", "description": message.content}]
        })
        await cl.Message(content="✏️ プランを修正し、リサーチを開始します。").send()
        await execute_research(graph, None, config_dict)

async def execute_research(graph, input_state, config_dict):
    config = config_dict["configurable"]["config"]
    ui_manager = cl.user_session.get("ui_manager")
    
    try:
        async for event in graph.astream(input_state, config_dict):
            node_name = list(event.keys())[0]
            # State can be large, only get what's needed or use get_state for accumulation
            full_state = graph.get_state(config_dict).values
            
            if node_name == "planner":
                plan = full_state.get("plan", [])
                plan_text = "### 📋 リサーチ計画案\n"
                for i, p in enumerate(plan):
                    plan_text += f"{i+1}. **{p['title']}**: {p['description']}\n"
                
                if config.INTERACTIVE_MODE and not full_state.get("plan_approved"):
                    plan_text += "\n\n---\n⚠️ **このプランで進めてよろしいですか？**\n`はい` または `OK` で承認、別の指示を入力するとプランを修正します。"
                    await cl.Message(content=plan_text).send()
                else:
                    async with cl.Step(name="研究計画の策定") as step:
                        step.output = plan_text

            elif node_name == "researcher" and config.INTERACTIVE_MODE:
                # In sequential mode, show current progress
                idx = full_state.get("current_section_index", 0)
                plan = full_state.get("plan", [])
                total = len(plan)
                query = full_state.get("current_query", "検索中...")
                
                async with cl.Step(name=f"調査中: {plan[idx]['title'] if idx < total else '最終段階'}") as step:
                    step.output = f"🔍 検索中...\nクエリ: `{query}`"

            elif node_name == "reflector" and config.INTERACTIVE_MODE:
                # This node proposes the NEXT query
                next_query = event[node_name].get("current_query")
                if next_query:
                    await cl.Message(content=f"🧠 **分析完了。次の視点で深掘りします:**\n`{next_query}`").send()

            elif node_name == "skills_extractor":
                skill = event[node_name].get("newly_extracted_skill")
                if skill:
                    await cl.Message(content=f"💡 **新しいスキルを学習しました:** `{skill}`").send()

            elif node_name == "final_reporter":
                await cl.Message(content="📑 **最終レポートを作成中...**").send()

        # --- Check if Interrupted ---
        full_state = graph.get_state(config_dict)
        if full_state.next:
            logger.info(f"Research interrupted at: {full_state.next}. Waiting for user input.")
            return

        # --- Report Delivery ---
        report = full_state.values.get("final_report", "")
        
        if report:
            # Prepare files
            elements = await process_visual_summary(report)
            
            # Save full report as file
            with tempfile.NamedTemporaryFile(suffix=".md", prefix="final_report_", delete=False) as tf:
                md_path = tf.name
            with open(md_path, "w", encoding="utf-8") as f:
                f.write(report)
            elements.append(cl.File(name="research_report.md", path=md_path, display="side"))
            
            # Clean text for chat
            display_text = clean_report_for_display(report)
            
            # Truncate if too long for UI
            if len(display_text) > 15000:
                display_text = display_text[:15000] + "\n\n---\n\n> ⚠️ **レポートが長いため一部を省略しました。全内容は添付の `research_report.md` を参照してください。**"
            
            await cl.Message(content=display_text, elements=elements).send()
            
            # Session cleanup/maintenance
            cl.user_session.set("previous_context", report)
            cl.user_session.set("graph", None)
            logger.info("Research session completed successfully.")
        else:
            await cl.Message(content="⚠️ レポートの生成に失敗しました。").send()
            cl.user_session.set("graph", None)

    except Exception:
        err_msg = traceback.format_exc()
        logger.error(f"Execution Error: {err_msg}")
        await cl.Message(content=f"❌ **システムエラーが発生しました:**\n```python\n{err_msg}\n```").send()
        cl.user_session.set("graph", None)

if __name__ == "__main__":
    # Standard entry point for debugging, but typically run via `chainlit run`
    pass
