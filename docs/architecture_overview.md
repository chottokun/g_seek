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
- `chainlit_app.py`: Chainlit を用いた初期実装。
- `chainlit_app_v2.py`: `cl.Step` を導入したテスト実装。

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
