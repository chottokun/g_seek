import streamlit as st
import asyncio
import os
import sys
import re
import json
import tempfile
import logging
import traceback
import uuid
import html
from typing import Dict, List, Optional, Any
from pyvis.network import Network

# Adjust path to import from core
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from deep_research_project.config.config import Configuration
from deep_research_project.core.graph import create_research_graph
from deep_research_project.tools.llm_client import LLMClient
from deep_research_project.tools.search_client import SearchClient
from deep_research_project.tools.content_retriever import ContentRetriever
from langgraph.checkpoint.memory import MemorySaver

# Logger setup
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# --- Utility Functions ---

def robust_json_repair(json_str: str):
    """Attempts to repair common LLM JSON output issues."""
    json_str = json_str.strip()
    if not json_str: return None
    json_str = re.sub(r'^```json\s*', '', json_str)
    json_str = re.sub(r'\s*```$', '', json_str)
    try:
        return json.loads(json_str)
    except json.JSONDecodeError:
        for i in range(1, 10):
            try: return json.loads(json_str + '}' * i)
            except: continue
        last_brace = json_str.rfind('}')
        if last_brace != -1:
            try: return json.loads(json_str[:last_brace+1])
            except: pass
    return None

def create_viz_html(report: str):
    """Generates HTML strings for network visualizations found in the report."""
    json_pattern = r"```json\s*\n(.*?)\n?```"
    json_matches = re.findall(json_pattern, report, re.DOTALL)
    if not json_matches:
        raw_match = re.search(r"(\{.*\"nodes\".*\"edges\".*\})", report, re.DOTALL | re.IGNORECASE)
        if raw_match: json_matches = [raw_match.group(1)]
            
    html_files = []
    for idx, json_str in enumerate(json_matches):
        data = robust_json_repair(json_str)
        if not data or 'nodes' not in data: continue
        try:
            net = Network(notebook=False, height="600px", width="100%", directed=True)
            net.set_options('{"physics": {"enabled": true}}')
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
            
            with tempfile.NamedTemporaryFile(suffix=".html", delete=False) as tf:
                tmp_path = tf.name
            net.save_graph(tmp_path)
            with open(tmp_path, "r", encoding="utf-8") as f:
                html_files.append({"name": f"Visual_Summary_{idx+1}.html", "content": f.read()})
            os.unlink(tmp_path)
        except Exception as e:
            logger.error(f"Visualization error: {e}")
    return html_files

# --- UI Application ---

async def run_research_graph(topic: str, config: Configuration, language: str):
    """Executes the LangGraph research workflow and updates the UI state."""
    # 1. Initialization
    llm = LLMClient(config)
    search = SearchClient(config)
    retriever = ContentRetriever(config)
    graph = create_research_graph(config, llm, search, retriever)
    
    thread_id = str(uuid.uuid4())
    st.session_state.thread_id = thread_id
    st.session_state.graph = graph
    st.session_state.logs = [] 
    st.session_state.app_config = config
    
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
    
    # UI Setup
    status_placeholder = st.empty()
    with status_placeholder.status("🚀 リサーチ進行中...", expanded=True) as status:
        p_bar = st.progress(0, text="準備中...")

        async def progress_cb(msg: str):
            st.session_state.logs.append(msg)
            status.write(msg) # Write directly to status for guaranteed visibility
            
            # Progress bar logic
            if "Section" in msg and "/" in msg:
                try:
                    # Extract "Section X/Y"
                    match = re.search(r"Section (\d+)/(\d+)", msg)
                    if match:
                        current = int(match.group(1))
                        total = int(match.group(2))
                        p_bar.progress(current / total, text=f"進捗: セクション {current}/{total}")
                except: pass
            
        config_dict = {
            "configurable": {
                "thread_id": thread_id,
                "config": config,
                "progress_callback": progress_cb
            }
        }
        
        # 2. Execution Loop
        try:
            async for event in graph.astream(initial_state, config_dict):
                node_name = list(event.keys())[0]
                full_state = graph.get_state(config_dict).values
                
                if node_name == "planner":
                    status.write("📋 リサーチ計画が生成されました。")
                    if config.INTERACTIVE_MODE and not full_state.get("plan_approved"):
                        st.session_state.interrupted = True
                        status.update(label="✋ 計画の承認待ち", state="complete", expanded=True)
                        break
                elif node_name == "researcher":
                    query = full_state.get("current_query", "検索中...")
                    status.write(f"🔍 クエリ実行: `{query}`")
                elif node_name == "final_reporter":
                    status.write("📑 最終レポートを合成中...")
            
            # 3. Completion
            final_state = graph.get_state(config_dict).values
            st.session_state.final_report = final_state.get("final_report", "")
            if st.session_state.final_report:
                status.update(label="✅ 全て完了しました！", state="complete", expanded=False)
            
        except Exception as e:
            st.error(f"エラーが発生しました: {str(e)}")
            logger.error(traceback.format_exc())

def main():
    st.set_page_config(page_title="Deep Research AI", page_icon="🔬", layout="wide")
    
    st.title("🔬 Deep Research Assistant")

    # State Initialization
    if "final_report" not in st.session_state: st.session_state.final_report = ""
    if "thread_id" not in st.session_state: st.session_state.thread_id = None
    if "interrupted" not in st.session_state: st.session_state.interrupted = False
    if "logs" not in st.session_state: st.session_state.logs = []
    if "executing" not in st.session_state: st.session_state.executing = False
    if "start_requested" not in st.session_state: st.session_state.start_requested = False
    if "resume_requested" not in st.session_state: st.session_state.resume_requested = False

    # Sidebar Settings
    with st.sidebar:
        st.header("⚙️ システム設定")
        config = Configuration()
        
        language = st.selectbox("出力言語", ["Japanese", "English"], index=0, disabled=st.session_state.executing)
        
        st.subheader("対話オプション")
        interactive = st.toggle("リサーチ計画を自分で編集・承認する", value=config.INTERACTIVE_MODE, help="ONにすると、調査開始前にAIが作成したプランを確認・修正できます。", disabled=st.session_state.executing)
        
        st.subheader("詳細設定")
        snippets_only = st.toggle("高速モード (スニペットのみ使用)", value=config.USE_SNIPPETS_ONLY_MODE, disabled=st.session_state.executing)
        max_loops = st.slider("最大試行回数 (セクション毎)", 1, 10, config.MAX_RESEARCH_LOOPS, disabled=st.session_state.executing)
        
        if st.button("🗑️ セッションをリセット", disabled=st.session_state.executing):
            for key in list(st.session_state.keys()):
                del st.session_state[key]
            st.rerun()

    # --- 1. Start Research Execution ---
    if st.session_state.start_requested:
        st.session_state.start_requested = False
        st.session_state.executing = True
        
        config.INTERACTIVE_MODE = interactive
        config.USE_SNIPPETS_ONLY_MODE = snippets_only
        config.MAX_RESEARCH_LOOPS = max_loops
        
        asyncio.run(run_research_graph(st.session_state.current_topic, config, language))
        st.session_state.executing = False
        st.rerun()

    # --- 2. Resume Research Execution ---
    if st.session_state.resume_requested:
        st.session_state.resume_requested = False
        st.session_state.executing = True
        
        async def resume():
            status_placeholder = st.empty()
            with status_placeholder.status("🚀 調査を継続中...", expanded=True) as status:
                # Show historical logs
                for old_log in st.session_state.logs:
                    status.write(old_log)
                
                async def cb(m):
                    st.session_state.logs.append(m)
                    status.write(m) # Direct write to status
                    
                conf = {
                    "configurable": {
                        "thread_id": st.session_state.thread_id, 
                        "progress_callback": cb,
                        "config": st.session_state.app_config
                    }
                }
                async for _ in st.session_state.graph.astream(None, conf):
                    pass
                
                final_v = st.session_state.graph.get_state(conf).values
                st.session_state.final_report = final_v.get("final_report", "")
                status.update(label="✅ リサーチ完了！", state="complete", expanded=False)
        
        asyncio.run(resume())
        st.session_state.executing = False
        st.rerun()

    # --- 3. Input Area ---
    if not st.session_state.final_report and not st.session_state.interrupted and not st.session_state.executing:
        st.markdown("### 🔍 新しいリサーチを開始")
        topic = st.text_area("調査したいテーマを入力してください:", placeholder="例: 日本の生成AI市場の現状と2025年までの予測", height=100)
        
        if st.button("🚀 調査開始", type="primary"):
            if not topic:
                st.warning("テーマを入力してください。")
            else:
                st.session_state.current_topic = topic
                st.session_state.final_report = ""
                st.session_state.interrupted = False
                st.session_state.start_requested = True
                st.rerun()

    # --- 4. Plan Approval UI ---
    if st.session_state.interrupted and not st.session_state.executing:
        st.divider()
        st.subheader("📋 リサーチ計画の確認・修正")
        st.info("AIが提案した以下の計画を修正・承認してください。各項目は編集可能です。")
        
        config_dict = {"configurable": {"thread_id": st.session_state.thread_id}}
        full_state = st.session_state.graph.get_state(config_dict).values
        current_plan = full_state.get("plan", [])
        
        edited_plan = []
        for i, p in enumerate(current_plan):
            with st.expander(f"セクション {i+1}: {p['title']}", expanded=True):
                new_title = st.text_input(f"タイトル {i+1}", value=p['title'], key=f"title_{i}")
                new_desc = st.text_area(f"調査内容 {i+1}", value=p['description'], key=f"desc_{i}")
                edited_plan.append({"title": new_title, "description": new_desc})
        
        col_ok, col_ng = st.columns([1, 4])
        with col_ok:
            if st.button("✅ 修正を反映して開始", type="primary"):
                st.session_state.graph.update_state(config_dict, {
                    "plan": edited_plan,
                    "plan_approved": True
                })
                st.session_state.interrupted = False
                st.session_state.resume_requested = True
                st.rerun()
        with col_ng:
            if st.button("❌ キャンセル"):
                st.session_state.interrupted = False
                st.session_state.thread_id = None
                st.rerun()

    # --- 5. Display Results ---
    if st.session_state.final_report:
        st.divider()
        st.subheader("📑 リサーチレポート")
        
        # Download Section
        dcol1, dcol2 = st.columns(2)
        with dcol1:
            st.download_button(
                label="📥 レポート (Markdown) を保存",
                data=st.session_state.final_report,
                file_name=f"research_report_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.md",
                mime="text/markdown",
                key="dl_report"
            )
        
        # Visual Summaries (HTML)
        viz_files = create_viz_html(st.session_state.final_report)
        if viz_files:
            with dcol2:
                for vf in viz_files:
                    st.download_button(
                        label=f"📊 {vf['name']} を保存",
                        data=vf['content'],
                        file_name=vf['name'],
                        mime="text/html",
                        key=f"dl_{vf['name']}"
                    )
        
        # Content Tabs
        tab1, tab2, tab3 = st.tabs(["📄 レポート本文", "🕸️ ネットワーク図", "📋 コピー用"])
        
        with tab1:
            # Display cleaned markdown
            clean_md = re.sub(r'##\s*(?:Visual\s*Summary|視覚的要約).*?(?=##|---|$)', '', st.session_state.final_report, flags=re.DOTALL | re.IGNORECASE)
            clean_md = re.sub(r'```json.*?```', '', clean_md, flags=re.DOTALL)
            st.markdown(clean_md)
            
        with tab2:
            if viz_files:
                for vf in viz_files:
                    st.markdown(f"#### {vf['name']}")
                    st.components.v1.html(vf['content'], height=600, scrolling=True)
            else:
                st.info("このレポートにはネットワーク図が含まれていません。")
                
        with tab3:
            st.info("以下のエリアを選択してコピーしてください。")
            st.text_area("Markdown Source", value=st.session_state.final_report, height=600)

if __name__ == "__main__":
    import datetime
    main()
