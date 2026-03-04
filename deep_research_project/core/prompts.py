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

SUMMARIZE_CHUNK_PROMPT_JA = "リサーチクエリ: '{query}' のために、このセグメントを要約してください。\n\nセグメント:\n{chunk}"
SUMMARIZE_CHUNK_PROMPT_EN = "Summarize this segment for the research query: '{query}'.\n\nSegment:\n{chunk}"

SUMMARIES_SYNTHESIS_PROMPT_JA = "これらの要約を、クエリ: '{query}' に関する一つの首尾一貫した要約にまとめてください。\n\n要約群:\n{combined}"
SUMMARIES_SYNTHESIS_PROMPT_EN = "Combine these summaries into one coherent summary for query: '{query}'.\n\nSummaries:\n{combined}"

RELEVANCE_SCORE_PROMPT_JA = """クエリ: {query}

検索結果:
タイトル: {title}
スニペット: {snippet}

このページがクエリに関連しているかを 0.0〜1.0 でスコアリングしてください。
- 1.0: 非常に関連性が高い
- 0.5: やや関連性がある
- 0.0: 全く関連性がない

スコアのみを数値で回答してください（例: 0.8）
"""

RELEVANCE_SCORE_PROMPT_EN = """Query: {query}

Search Result:
Title: {title}
Snippet: {snippet}

Score the relevance of this page to the query on a scale of 0.0 to 1.0.
- 1.0: Highly relevant
- 0.5: Somewhat relevant
- 0.0: Not relevant

Respond with only the numeric score (e.g., 0.8)
"""

REGENERATE_QUERY_PROMPT_JA = """トピック: {topic}
セクション: {section_title}
元のクエリ: {original_query}

このクエリでは関連性の高い検索結果が見つかりませんでした。
より適切な検索クエリを生成してください。以下の点を考慮してください:
- より具体的なキーワードを使用
- 別の表現や類義語を試す
- 検索範囲を広げる（または狭める）

新しい検索クエリのみを出力してください（説明不要）。
"""

REGENERATE_QUERY_PROMPT_EN = """Topic: {topic}
Section: {section_title}
Original Query: {original_query}

This query did not yield any relevant search results.
Generate a more appropriate search query. Consider:
- Using more specific keywords
- Trying alternative expressions or synonyms
- Broadening (or narrowing) the search scope

Output only the new search query (no explanation needed).
"""

REFLECT_AND_DECIDE_PROMPT_JA = """リサーチトピック: {topic}
セクション: {section_title}
セクションの目的: {section_description}
現在の要約:
{accumulated_summary}

このセクションにさらなる調査が必要かどうかを評価してください。
必要な場合、次に調査すべき具体的な検索クエリを生成してください。
クエリは以下の条件を満たす必要があります:
- リサーチトピック '{topic}' との関連性を保つ
- セクション '{section_title}' の目的に直接関連する
- これまでの要約で既にカバーされていない新しい側面を探る
- 具体的で検索エンジンで有効な形式

フォーマット: EVALUATION: <CONTINUE|CONCLUDE>
QUERY: <次の検索クエリまたは None>"""

REFLECT_AND_DECIDE_PROMPT_EN = """Research Topic: {topic}
Section: {section_title}
Section Purpose: {section_description}
Current Summary:
{accumulated_summary}

Evaluate if more research is needed for this section.
If needed, generate a specific search query for the next investigation.
The query must meet the following criteria:
- Maintain relevance to the research topic '{topic}'
- Directly relate to the section '{section_title}' purpose
- Explore new aspects not already covered in the summary
- Be specific and effective for search engines

Format: EVALUATION: <CONTINUE|CONCLUDE>
QUERY: <Next search query or None>"""

FINAL_REPORT_PROMPT_JA = """トピック: {topic} に関する最終リサーチレポートを作成してください。

コンテキスト:
{full_context}

{source_info}

指示: 包括的で専門的な構成（日本語）にしてください。{citation_instruction}"""

FINAL_REPORT_PROMPT_EN = """Synthesize a final report for: {topic}

Context:
{full_context}

{source_info}

Instruction: Professional structure. {citation_instruction}"""
