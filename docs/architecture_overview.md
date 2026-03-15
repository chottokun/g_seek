# Deep Research System Architecture Overview

このプロジェクトは、LangGraph を用いた階層的なリサーチ自動化ツールです。

## 主要コンポーネント

### 1. コアロジック (deep_research_project/core/)
- `graph.py`: リサーチ全体のワークフローを定義。`planner`, `researcher`, `reflector`, `skills_extractor`, `final_reporter` の各ノードを繋ぐ。
- `research_loop.py`: 非対話モード (並列実行) の際のリサーチ実行ループ。セクションごとに独立したリサーチを回す。
- `planning.py`: リサーチ計画案 (Plan) の生成。
- `execution.py`: Web 検索、情報のフィルタリング、要約。
- `reflection.py`: 収集した情報の評価と、必要に応じた追加クエリの提案。知識グラフ (Knowledge Graph) の抽出も行う。
- `reporting.py`: 最終的なリサーチレポートの生成。
- `skills_manager.py`: 過去のリサーチから「スキル」を抽出し、動的に活用する仕組み。

### 2. ツール (deep_research_project/tools/)
- `llm_client.py`: OpenAI, Gemini, Ollama などの各 LLM API への汎用インターフェース。
- `search_client.py`: SearXNG, Tavily などの検索エンジンへのアクセス。
- `content_retriever.py`: Web ページや PDF のコンテンツ取得。

### 3. UI (deep_research_project/)
- **`streamlit_app.py` (メイン UI)**: 安定性と高機能性を兼ね備えた Streamlit 版インターフェース。
  - `st.status` による動的進捗表示。
  - `st.download_button` による確実な成果物（MD, HTML）提供。
  - インラインでのリサーチプラン編集機能。
- `chainlit_app.py`: Chainlit を用いた参考実装。一部の環境でファイル提供に制限がある。

## リサーチの流れ

1. **Planner**: ユーザーのテーマに基づき、複数のセクションからなるリサーチ計画を作成。
   - (対話モード時はここで中断し、ユーザーの承認を待つ)
2. **Researcher**: 各セクションに対して、検索クエリを発行し Web 検索を実行。
3. **Reflector**: 取得した情報を評価し、さらに深掘りが必要な場合は Researcher に戻る。十分な情報が集まったら次のセクションへ。
   - 非対話モード時は `ResearchLoop` により、各セクションのリサーチが並列で実行される。
4. **Skills Extractor**: リサーチ結果から将来活用可能な知見やパターンをスキルとして保存。
5. **Final Reporter**: 全ての結果を統合し、構造化されたレポートを生成。視覚的要約 (JSON) も含める。

## UI 実装のポイント
Chainlit 側では、LangGraph の `astream` を監視しつつ、`ResearchLoop` からの進捗コールバックも適切に表示する必要がある。
特に、並列実行される各セクションのステータス更新をユーザーに分かりやすく伝えることが重要。

### 安定性とセキュリティ
1. **スレッドセーフなファイル提供 (Streamlit)**: 各セッションの状態を `st.session_state` で独立して管理。成果物はメモリ上で生成され、ブラウザの標準的なダウンロード機能を通じて安全に提供される。
2. **堅牢なスキル管理**: スキル抽出時に具体的な「知見の要約」をメタデータ（description）として保存することで、将来のリサーチにおける選択精度を大幅に向上させた。
3. **並列実行の制御**: `ResearchLoop` 内のセマフォをインスタンスレベルで管理し、複数のリサーチが異なるイベントループで実行された際の競合を回避。
