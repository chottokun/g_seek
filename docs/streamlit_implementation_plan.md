# Streamlit UI 実装計画

## 概要
Chainlit で課題となった「ファイルダウンロードの不安定さ」を解決し、リサーチの進捗可視化と最終成果物の提供を確実に行える安定した UI を構築する。

## 実装の柱

### 1. LangGraph ワークフローとの統合
- 現在の `streamlit_app.py` は `ResearchLoop` を直接呼び出しているが、これを `core/graph.py` の `create_research_graph` を使う形式に刷新する。
- `st.session_state` にグラフのステートを保持し、再描画（rerun）に対応する。

### 2. 進捗状況のリアルタイム表示
- `st.status` を活用し、現在実行中のノード（Planner, Researcher 等）や検索クエリをリアルタイムに表示する。
- 非対話モードでの並列実行時も、各セクションのステータスを一覧できるようにする。

### 3. 多彩なダウンロードオプション
- **Markdown レポート**: `st.download_button` で全文を提供。
- **視覚的要約 (HTML)**: レポート内の JSON から `pyvis` ネットワーク図を動的に生成し、HTML ファイルとしてダウンロード可能にする。
- **知識グラフ (Interactive)**: `streamlit-agraph` または埋め込み HTML により、ブラウザ上でグラフを操作・閲覧できるようにする。

### 4. 対話型承認フロー
- プランの承認やクエリの修正を `st.text_input` や `st.button` を使って実装。
- ユーザーの入力を待つ際、グラフの中断状態（Interrupt）を正しくハンドリングする。

## タスクリスト
- [ ] `streamlit_app.py` のコアロジックを LangGraph (graph.py) ベースに書き換え。
- [ ] `ProgressHandler` クラスの実装（コールバック情報を Streamlit の `st.status` に流し込む）。
- [ ] ネットワーク図 (HTML) の生成とダウンロードボタンの実装。
- [ ] 最終レポートのクリップボードコピー用 `st.text_area` の追加。
- [ ] 動作確認とデバッグ。
