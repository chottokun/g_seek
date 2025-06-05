# Deep Research Project

AIを活用したリサーチ自動化ツールです。  
LLM（大規模言語モデル）とWeb検索API（DuckDuckGo, SearxNG等）を組み合わせて、指定トピックの調査・レポート生成を行います。

## 狙い
Google社のAIコーディングアシスタント[Jules](https://jules.google.com/)を利用した実装の勉強

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

### 3. SearxNGの利用について

- 自前でSearxNGサーバーを立てる場合は、`settings.yml` でAPIアクセスが許可されていることを確認してください。
- パブリックSearxNGインスタンスの多くはAPI/botアクセスを制限しています。403 Forbiddenエラーが出る場合はサーバー設定を見直すか、自前サーバーを推奨します。

## 実行方法

```bash
uv run -m deep_research_project.main
```

## カスタマイズ

- 調査トピックは `deep_research_project/main.py` の `research_topic` 変数で指定できます。
- ループ回数や出力ファイル名は `.env` で調整可能です。

## ログ・レポート

- 実行ログは標準出力に出ます。
- 最終レポートは `OUTPUT_FILENAME` で指定したファイルに保存されます。

---

**注意:**  
SearxNGのAPI利用にはサーバー側の設定が必要です。403エラー等が出る場合はREADME内の「SearxNGの利用について」を参照してください。