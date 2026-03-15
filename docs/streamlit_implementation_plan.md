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

## 最終的な達成内容
- **LangGraph への完全移行**: `ResearchLoop` 直接呼び出しから、`graph.py` のステートマシン実行へと刷新。
- **頑健なダウンロード機能**: `st.download_button` により、Markdown レポートと Pyvis HTML ネットワーク図の確実な提供を実現。
- **高度な UI 制御**: 
  - リサーチ計画のインライン編集機能を実装。
  - スクロール可能なログコンテナとプログレスバーによる洗練された進捗表示。
  - 二重実行防止や状態復元を含む厳密なセッション管理。
- **技術的課題の克服**: 
  - `asyncio.Semaphore` のイベントループ不整合問題を、インスタンスレベルでの管理により解消。
  - `await asyncio.sleep(0)` による非同期 UI フラッシュの最適化。

## タスクリスト
- [x] `streamlit_app.py` のコアロジックを LangGraph (graph.py) ベースに書き換え。
- [x] `ProgressHandler` クラスの実装（コールバック情報を Streamlit の `st.status` に流し込む）。
- [x] ネットワーク図 (HTML) の生成とダウンロードボタンの実装。
- [x] 最終レポートのクリップボードコピー用 `st.text_area` の追加。
- [x] 動作確認とデバッグ（イベントループエラー、レイアウト崩れ、二重送信の修正）。
