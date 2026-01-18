# Research Assistant

AIを活用したリサーチ自動化ツールです。  
LLM（大規模言語モデル）とWeb検索API（DuckDuckGo, SearxNG）を最適に組み合わせて、指定トピックの深層調査・構造化レポート生成を行います。最新の `uv` を活用した高速なパッケージ管理と、Docker環境での実行に対応しています。

## 狙い
Google社のAIコーディングアシスタント[Jules](https://jules.google.com/)等のエージェント型AIの活用学習を目的とした、実戦的なリサーチエージェントの開発。

## 特徴

- **三段階のリサーチプロセス**: 計画（Planning）→ 実行（Execution）→ 統合（Synthesis）のステップによる高度なレポート作成
- **インタラクティブ・モード**: リサーチ計画の修正や、検索結果の取捨選択を人間が介在して調整可能
- **マルチプロバイダー対応**: Ollama, OpenAI, Azure OpenAI 等のLLM、SearxNG, DuckDuckGo 等の検索エンジンを切り替え可能
- **高速な環境構築**: `uv` による決定論的で高速なパッケージ管理
- **コンテナ化**: Docker / Docker Compose ですぐに開発・実行環境を立ち上げ可能

## セットアップ

### 1. `uv` を使用したローカル開発環境

本プロジェクトではパッケージ管理に [uv](https://github.com/astral-sh/uv) を推奨しています。

```bash
# 依存関係のインストール
uv sync

# 仮想環境の有効化（オプション）
source .venv/bin/activate
```

### 2. 環境変数の設定

`.env` ファイルをプロジェクトルートに作成（`.env.example` をコピー）し、必要事項を入力してください。

```bash
cp .env.example .env
```

主な設定項目:
- `LLM_PROVIDER`: `ollama`, `openai`, `azure` 等
- `SEARCH_API`: `searxng`, `duckduckgo` 等
- `MAX_RESEARCH_LOOPS`: 最大ループ回数（デフォルト 3）

## 実行方法

### Streamlit UI (推奨)
ブラウザから直感的にリサーチを指示・確認できます。

```bash
uv run streamlit run deep_research_project/streamlit_app.py
```
デフォルトで http://localhost:8501 でアクセス可能です。

### CLI (テスト用)
コマンドラインから素早くプログラムをテストできます。

```bash
uv run -m deep_research_project.main
```

### Docker Compose
SearxNG等を含めたフルスタック環境をワンコマンドで起動できます。

```bash
docker-compose up -d
```

## ドキュメント

- [Architecture.md](./Architecture.md): システム構成とワークフローの詳細
- [tips.md](./tips.md): 開発・デバッグ時の知見
- [docs/improvements_and_refactoring.md](./docs/improvements_and_refactoring.md): リファクタリングの履歴と改善点

---

**注意:**  
- Streamlit UI利用時、ステータス更新がリアルタイムで行われますが、複数タブでの同時操作は推奨されません。
- SearxNGを利用する場合は、別途SearxNGサーバーが稼働している必要があります（Docker Compose利用時は自動で含まれます）。