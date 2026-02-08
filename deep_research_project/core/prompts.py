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
