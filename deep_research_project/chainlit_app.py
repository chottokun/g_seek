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
import aiofiles
from typing import Dict, Optional
from pyvis.network import Network

# Ensure imports from parent directory
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from deep_research_project.config.config import Configuration
from deep_research_project.core.graph import create_research_graph
from deep_research_project.tools.llm_client import LLMClient
from deep_research_project.tools.search_client import SearchClient
from deep_research_project.tools.content_retriever import ContentRetriever
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
                # Use a fixed name for the Step to avoid avatar lookup errors with long dynamic titles
                step = cl.Step(name="Researcher", parent_id=self.main_step.id if self.main_step else None)
                await step.send()
                self.section_steps[section_title] = step
            
            # Update the section step with the dynamic title and details
            self.section_steps[section_title].output = f"### {section_title}\n{details}"
            await self.section_steps[section_title].update()
        else:
            # General progress message
            if "Processing" in msg and "parallel" in msg:
                # Start of parallel processing
                self.main_step = cl.Step(name="Manager")
                self.main_step.output = msg
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
    if not json_str:
        return None
    
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
            except Exception:
                continue
            
        # Try to find the last complete object
        last_brace = json_str.rfind('}')
        if last_brace != -1:
            try:
                return json.loads(json_str[:last_brace+1])
            except Exception:
                pass
            
    return None

async def process_visual_summary(report: str, thread_id: str, tmp_dir: str):
    """Extracts Visual Summary JSON and creates temporary HTML files for visualization."""
    # Pattern to match JSON blocks
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
            json_obj = robust_json_repair(json_str)
            if not json_obj or "nodes" not in json_obj:
                continue

            net = Network(notebook=False, height="600px", width="100%", directed=True)
            # Options for a nicer look
            net.set_options("""
            var options = { "physics": { "barnesHut": { "gravitationalConstant": -3000, "centralGravity": 0.3, "springLength": 150 } } }
            """)
            
            for node in json_obj.get('nodes', []):
                color = "#ff9999" if node.get('type') == 'core' else "#99ccff"
                label = node.get('label', str(node.get('id', '')))
                title_html = f"<b>{label}</b>"
                if 'description' in node and node['description']:
                    title_html += f"<br><br>{node['description']}"
                if 'url' in node and node['url']:
                    title_html += f"<br><br><a href='{node['url']}' target='_blank'>[出典リンクを開く]</a>"
                net.add_node(node.get('id'), label=label, color=color, shape="box", title=title_html)
                
            for edge in json_obj.get('edges', []):
                net.add_edge(str(edge['from']), str(edge['to']), title=edge.get('label', ''), label=edge.get('label', ''))
            
            tmp_path = os.path.join(tmp_dir, f"visual_summary_{idx}.html")
            
            # Use to_thread to keep I/O from blocking the event loop
            await asyncio.to_thread(net.save_graph, tmp_path)
            
            async with aiofiles.open(tmp_path, mode="r", encoding="utf-8") as f:
                content = await f.read()
            
            file_elements.append(
                cl.File(
                    name=f"Visual_Summary_{idx+1}.html",
                    content=content,
                    display="inline"
                )
            )
        except Exception:
            logger.error(f"Failed to process graph {idx}: {traceback.format_exc()}")
            
    return file_elements

def clean_report_for_display(report: str):
    """Removes the large JSON blocks and internal technical sections from the chat display."""
    # Remove Visual Summary section completely from chat display
    report = re.sub(r'##\s*(?:Visual\s*Summary|視覚的要約).*?(?=##|---|$)', '', report, flags=re.DOTALL | re.IGNORECASE)
    # Remove any remaining raw JSON blocks
    report = re.sub(r'```json.*?```', '', report, flags=re.DOTALL)
    return report.strip()

# --- Action Callbacks ---

@cl.action_callback("copy_report")
async def on_copy_report(action: cl.Action):
    """Sends the full report in a code block for easy copying."""
    logger.info("Copy report action triggered.")
    full_report = cl.user_session.get("full_report")
    
    if full_report:
        # Inform the user what to do next
        await cl.Message(
            content=(
                "### 📋 レポート全文 (コピー用)\n"
                "以下のブロックの右上にある **'Copy'** ボタンをクリックしてください。\n"
                "※ ボタンが表示されない場合は、枠内のテキストを全選択してコピーしてください。\n\n"
                f"```markdown\n{full_report}\n```"
            )
        ).send()
        logger.info(f"Full report sent to UI for copying (Length: {len(full_report)})")
    else:
        logger.error("Failed to find full_report in user_session.")
        await cl.Message(content="⚠️ レポートのデータがセッション内に見つかりませんでした。再度リサーチを実行してください。").send()

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
    thread_id = config_dict["configurable"]["thread_id"]
    
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
                    async with cl.Step(name="Planner") as step:
                        step.output = plan_text

            elif node_name == "researcher" and config.INTERACTIVE_MODE:
                # In sequential mode, show current progress
                idx = full_state.get("current_section_index", 0)
                plan = full_state.get("plan", [])
                total = len(plan)
                query = full_state.get("current_query", "検索中...")
                section_title = plan[idx]['title'] if idx < total else '最終段階'
                
                async with cl.Step(name="Researcher") as step:
                    step.output = f"🔍 調査中: **{section_title}**\nクエリ: `{query}`"

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
        # Store in session for the action callback
        cl.user_session.set("full_report", report)
        
        if report:
            with tempfile.TemporaryDirectory() as tmp_dir:
                # 1. Non-blocking Visual Summary processing (from PR #89)
                file_elements = await process_visual_summary(report, thread_id, tmp_dir)
                
                # 2. Non-blocking Report File Creation
                try:
                    file_elements.append(
                        cl.File(
                            name="Full_Research_Report.md",
                            content=report,
                            display="inline"
                        )
                    )
                except Exception:
                    logger.error(f"Failed to save report file: {traceback.format_exc()}")

                # 3. Clean text for chat display
                display_text = clean_report_for_display(report)

                # 4. Prepare the action button
                actions = [
                    cl.Action(name="copy_report", value="copy", label="📋 全文をコピー用に表示", payload={})
                ]

                # Truncate preview if very long
                if len(display_text) > 10000:
                    display_text = display_text[:10000] + "\n\n---\n> ⚠️ **レポートが長いため一部を省略しました。全内容は下のボタンを押して取得してください。**"

                # Final message with elements (Downloadable report and HTML visualization)
                await cl.Message(content=display_text, actions=actions, elements=file_elements).send()
            
            # Reset session for next research
            cl.user_session.set("previous_context", report)
            cl.user_session.set("graph", None)
            logger.info("Research completed. Action button and file elements sent.")
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
