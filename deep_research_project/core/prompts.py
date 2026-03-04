# Language independent prompts could go here, but we focus on modularizing the loop's prompts.

RESEARCH_PLAN_PROMPT_JA = (
    "トピック: '{topic}' に関する詳細なリサーチプランを生成してください。\n"
    "プランは少なくとも {min_sections} つ、最大 {max_sections} つのセクションで構成してください。\n"
    "各セクションには明確なタイトルと、そのセクションで何を調査すべきかの詳細な説明を含めてください。"
)

RESEARCH_PLAN_PROMPT_EN = (
    "Generate a detailed research plan for the topic: '{topic}'.\n"
    "The plan should have at least {min_sections} and at most {max_sections} sections.\n"
    "Each section must have a clear title and a detailed description of what to research."
)


INITIAL_QUERY_PROMPT_JA = (
    "リサーチトピック: '{topic}'\n"
    "セクション: '{section_title}'\n"
    "セクションの目的: '{section_description}'\n\n"
    "このセクションの目的を達成するための、具体的で焦点を絞った検索クエリを 1 つ生成してください。\n"
    "クエリは以下の条件を満たす必要があります:\n"
    "- リサーチトピック全体との関連性を保つ\n"
    "- セクションの目的に直接関連する\n"
    "- 具体的で検索エンジンで有効な形式\n\n"
    "出力は検索クエリ文字列のみにしてください。解説、マークダウン、引用符、前置きなどは一切含めないでください。"
)

INITIAL_QUERY_PROMPT_EN = (
    "Research Topic: '{topic}'\n"
    "Section: '{section_title}'\n"
    "Section Purpose: '{section_description}'\n\n"
    "Generate one specific, focused search query to achieve the purpose of this section.\n"
    "The query must meet the following criteria:\n"
    "- Maintain relevance to the overall research topic\n"
    "- Directly relate to the section's purpose\n"
    "- Be specific and effective for search engines\n\n"
    "Output ONLY the search query string. Do NOT include any explanations, markdown, quotes, or preambles."
)


# Add more prompts as needed for other modules
KG_EXTRACTION_PROMPT_JA = (
    "このテキストから主要なエンティティと関係を特定し、構造化データとして抽出してください:\n\n"
    "テキスト:\n{text}\n\n"
    "指針:\n"
    "1. エンティティのタイプを標準化してください（例: Person, Organization, Concept, Event, Technology, Location）。\n"
    "2. 各エンティティと関係に、テキストから得られる詳細なプロパティ（キー・値のペア）を含めてください。\n"
    "3. 可能な限り、以下のソースURLの中から該当するものを各項目に紐付けてください:\n"
    "{urls}\n"
    "4. properties には、'section': '{section_title}' を必ず含めてください。"
)

KG_EXTRACTION_PROMPT_EN = (
    "Identify and extract key entities and relationships from this text as structured data:\n\n"
    "Text:\n{text}\n\n"
    "Guidelines:\n"
    "1. Standardize entity types (e.g., Person, Organization, Concept, Event, Technology, Location).\n"
    "2. Include detailed properties (key-value pairs) for each entity and relationship found in the text.\n"
    "3. Link each item to relevant source URLs from this list if applicable:\n"
    "{urls}\n"
    "4. In properties, always include 'section': '{section_title}'."
)

# Reporting prompts
FINAL_REPORT_PROMPT_JA = (
    "トピック: {topic} に関する最終リサーチレポートを作成してください。\n\n"
    "コンテキスト:\n{full_context}\n\n"
    "{source_info}\n\n"
    "指示: 包括的で専門的な構成（日本語）にしてください。{citation_instruction}"
)

FINAL_REPORT_PROMPT_EN = (
    "Synthesize a final report for: {topic}\n\n"
    "Context:\n{full_context}\n\n"
    "{source_info}\n\n"
    "Instruction: Professional structure. {citation_instruction}"
)

CITATION_INSTRUCTION_JA = "番号付きのインライン引用 [1] を使用して出典を明記してください。"
CITATION_INSTRUCTION_EN = "Use numbered in-text citations like [1] to attribute information."

NO_CITATION_INSTRUCTION_JA = "引用は使用しないでください。"
NO_CITATION_INSTRUCTION_EN = "Do not use citations."

SOURCE_INFO_PROMPT_JA = "参考資料:\n{source_list}"
SOURCE_INFO_PROMPT_EN = "Reference Sources:\n{source_list}"

NO_SOURCE_INFO_MSG_JA = "Webソースは見つかりませんでした。"
NO_SOURCE_INFO_MSG_EN = "No web sources were found."

# Planning prompts
QUERY_REGEN_PROMPT_JA = (
    "トピック: {topic}\n"
    "セクション: {section_title}\n"
    "元のクエリ: {original_query}\n\n"
    "このクエリでは関連性の高い検索結果が見つかりませんでした。\n"
    "より適切な検索クエリを生成してください。以下の点を考慮してください:\n"
    "- より具体的なキーワードを使用\n"
    "- 別の表現や類義語を試す\n"
    "- 検索範囲を広げる（または狭める）\n\n"
    "新しい検索クエリのみを出力してください（説明不要）。"
)

QUERY_REGEN_PROMPT_EN = (
    "Topic: {topic}\n"
    "Section: {section_title}\n"
    "Original Query: {original_query}\n\n"
    "This query did not yield any relevant search results.\n"
    "Generate a more appropriate search query. Consider:\n"
    "- Using more specific keywords\n"
    "- Trying alternative expressions or synonyms\n"
    "- Broadening (or narrowing) the search scope\n\n"
    "Output only the new search query (no explanation needed)."
)

# Execution prompts
SUMMARIZE_CHUNK_PROMPT_JA = "リサーチクエリ: '{query}' のために、このセグメントを要約してください。\n\nセグメント:\n{chunk}"
SUMMARIZE_CHUNK_PROMPT_EN = "Summarize this segment for the research query: '{query}'.\n\nSegment:\n{chunk}"

SYNTHESIZE_SUMMARY_PROMPT_JA = "これらの要約を、クエリ: '{query}' に関する一つの首尾一貫した要約にまとめてください。\n\n要約群:\n{combined_summaries}"
SYNTHESIZE_SUMMARY_PROMPT_EN = "Combine these summaries into one coherent summary for query: '{query}'.\n\nSummaries:\n{combined_summaries}"

RELEVANCE_SCORE_PROMPT_JA = (
    "クエリ: {query}\n\n"
    "検索結果:\n"
    "タイトル: {title}\n"
    "スニペット: {snippet}\n\n"
    "このページがクエリに関連しているかを 0.0〜1.0 でスコアリングしてください。\n"
    "- 1.0: 非常に関連性が高い\n"
    "- 0.5: やや関連性がある\n"
    "- 0.0: 全く関連性がない\n\n"
    "スコアのみを数値で回答してください（例: 0.8）"
)

RELEVANCE_SCORE_PROMPT_EN = (
    "Query: {query}\n\n"
    "Search Result:\n"
    "Title: {title}\n"
    "Snippet: {snippet}\n\n"
    "Score the relevance of this page to the query on a scale of 0.0 to 1.0.\n"
    "- 1.0: Highly relevant\n"
    "- 0.5: Somewhat relevant\n"
    "- 0.0: Not relevant\n\n"
    "Respond with only the numeric score (e.g., 0.8)"
)

# Reflection prompts
REFLECTION_PROMPT_JA = (
    "リサーチトピック: {topic}\n"
    "セクション: {section_title}\n"
    "セクションの目的: {section_description}\n"
    "現在の要約:\n{accumulated_summary}\n\n"
    "このセクションにさらなる調査が必要かどうかを評価してください。\n"
    "必要な場合、次に調査すべき具体的な検索クエリを生成してください。\n"
    "クエリは以下の条件を満たす必要があります:\n"
    "- リサーチトピック '{topic}' との関連性を保つ\n"
    "- セクション '{section_title}' の目的に直接関連する\n"
    "- これまでの要約で既にカバーされていない新しい側面を探る\n"
    "- 具体的で検索エンジンで有効な形式\n\n"
    "フォーマット: EVALUATION: <CONTINUE|CONCLUDE>\nQUERY: <次の検索クエリまたは None>"
)

REFLECTION_PROMPT_EN = (
    "Research Topic: {topic}\n"
    "Section: {section_title}\n"
    "Section Purpose: {section_description}\n"
    "Current Summary:\n{accumulated_summary}\n\n"
    "Evaluate if more research is needed for this section.\n"
    "If needed, generate a specific search query for the next investigation.\n"
    "The query must meet the following criteria:\n"
    "- Maintain relevance to the research topic '{topic}'\n"
    "- Directly relate to the section '{section_title}' purpose\n"
    "- Explore new aspects not already covered in the summary\n"
    "- Be specific and effective for search engines\n\n"
    "Format: EVALUATION: <CONTINUE|CONCLUDE>\nQUERY: <Next search query or None>"
)

# Research Loop messages
NO_INFO_FOUND_MSG_JA = "クエリ「{query}」に関連する情報が見つかりませんでした。"
NO_INFO_FOUND_MSG_EN = "No relevant information found for query: '{query}'"

FOLLOW_UP_PROMPT_JA = (
    "以下のリサーチレポートに基づいて、ユーザーのフォローアップ質問に答えてください。\n\n"
    "レポート:\n{final_report}\n\n"
    "ユーザーの質問: {question}\n\n"
    "レポートの内容のみに基づいて、明確で簡潔な回答を提供してください。回答は日本語で行ってください。"
)

FOLLOW_UP_PROMPT_EN = (
    "Based on the following research report, answer the user's follow-up question.\n\n"
    "Report:\n{final_report}\n\n"
    "User Question: {question}\n\n"
    "Provide a clear and concise answer based only on the report content."
)
