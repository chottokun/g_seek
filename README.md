# Research Assistant

AIを活用したリサーチ自動化ツールにチャレンジします。。  
LLM（大規模言語モデル）とWeb検索API（DuckDuckGo, SearxNG等）を組み合わせて、指定トピックの調査・レポート生成を行います。基本的な操作を行うためのStreamlit UIも含まれています。

## 狙い
AIを活用したリサーチ自動化ツール「Research Assistant」の開発を通じて、Google社のAIコーディングアシスタント[Jules](https://jules.google.com/)の活用の勉強が目的です。

## 参考
以下の実装を参考にしました。
- Open Deep Research: https://github.com/langchain-ai/open_deep_research
- Local Deep Researcher: https://github.com/langchain-ai/local-deep-researcher

## 特徴

- LLMプロバイダー（例: Ollama）と検索API（DuckDuckGo, SearxNG）を切り替え可能
- 検索結果をもとに反復的にリサーチし、最終レポートを自動生成
- ログ出力・レポートファイル保存機能

## セットアップ

### 1. 必要なパッケージのインストール

```bash
pip install -r requirements.txt
```

### 2. 環境変数の設定

`.env` ファイルをプロジェクトルートに作成し、以下のように設定してください。

```
LLM_PROVIDER=ollama
SEARCH_API=searxng
SEARXNG_BASE_URL=http://localhost:8080
MAX_RESEARCH_LOOPS=3
LOG_LEVEL=INFO
OUTPUT_FILENAME=final_report.txt
```

DuckDuckGoを使う場合は `SEARCH_API=duckduckgo` にしてください。


## 実行方法

```bash
# streamlit UI
uv run streamlit run deep_research_project/streamlit_app.py
# CLI(テスト用)
uv run -m deep_research_project.main
```

- **Streamlit UIを利用する場合は、`.env`の設定内容が反映されます。設定を変更した場合は、再起動してください。**
- **StreamlitのWeb UIはデフォルトで http://localhost:8501 でアクセスできます。**

## カスタマイズ

- CLIの調査トピックは `deep_research_project/main.py` の `research_topic` 変数で指定できます。
- ループ回数や出力ファイル名は `.env` で調整可能です。

## ログ・レポート

- 実行ログは標準出力に出ます。
- 最終レポートは `OUTPUT_FILENAME` で指定したファイルに保存されます。

---

**注意:**  
- **Streamlit UI利用時は、複数タブや複数ユーザーで同時アクセスすると挙動が不安定になる場合があります。**