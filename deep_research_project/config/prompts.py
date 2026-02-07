PROMPTS = {
    "generate_research_plan": {
        "Japanese": (
            "以下のリサーチトピックに基づいて、{min_sec}〜{max_sec}つの主要なセクションで構成される構造化されたリサーチ計画を生成してください。\n"
            "リサーチトピック: {topic}\n\n"
            "各セクションについて、タイトルとリサーチすべき内容の簡潔な説明を提供してください。"
        ),
        "English": (
            "Based on the following research topic, generate a structured research plan consisting of {min_sec} to {max_sec} key sections.\n"
            "Research Topic: {topic}\n\n"
            "For each section, provide a title and a brief description of what should be researched."
        )
    },
    "generate_initial_query": {
        "Japanese": (
            "以下のリサーチタスクのために、簡潔なWeb検索クエリ（最大{max_words}単語）を生成してください。\n"
            "メインテーマ: {topic}\n"
            "セクション: {section_topic}\n"
            "説明: {description}\n\n"
            "クエリのみを出力してください。英語のソースも取得できるよう、適切であれば英語のクエリも検討してください。"
        ),
        "English": (
            "Generate a concise web search query (max {max_words} words) for the following research task.\n"
            "Main Topic: {topic}\n"
            "Section: {section_topic}\n"
            "Description: {description}\n\n"
            "Output only the query."
        )
    },
    "summarize_chunk": {
        "Japanese": "リサーチクエリ: '{query}' のために、このセグメントを要約してください。\n\nセグメント:\n{chunk}",
        "English": "Summarize this segment for the research query: '{query}'.\n\nSegment:\n{chunk}"
    },
    "combine_summaries": {
        "Japanese": "これらの要約を、クエリ: '{query}' に関する一つの首尾一貫した要約にまとめてください。\n\n要約群:\n{summaries}",
        "English": "Combine these summaries into one coherent summary for query: '{query}'.\n\nSummaries:\n{summaries}"
    },
    "extract_entities": {
        "Japanese": "このテキストから主要なエンティティと関係を特定してください:\n\n{text}",
        "English": "Identify key entities and relationships from this text:\n\n{text}"
    },
    "reflect_on_summary": {
        "Japanese": (
            "トピック: {topic}\n"
            "セクション: {section_title}\n"
            "現在の要約:\n{summary}\n\n"
            "このセクションにさらなる調査が必要かどうかを評価してください。"
            "フォーマット: EVALUATION: <CONTINUE|CONCLUDE>\nQUERY: <次の検索クエリまたは None>"
        ),
        "English": (
            "Topic: {topic}\n"
            "Section: {section_title}\n"
            "Current Summary:\n{summary}\n\n"
            "Evaluate if more research is needed for this section. "
            "Format: EVALUATION: <CONTINUE|CONCLUDE>\nQUERY: <Next search query or None>"
        )
    },
    "citation_instruction": {
        "Japanese": "上記のソースに情報を帰属させるために、[1]や[2, 3]のような番号付きのインライン引用を必ず使用してください。",
        "English": "You MUST use numbered in-text citations such as [1] or [2, 3] to attribute information to the sources listed above."
    },
    "finalize_summary": {
        "Japanese": (
            "トピック: {topic} に関する最終的なリサーチレポートを統合してください。\n\n"
            "リサーチコンテキスト（各セクションからの要約）:\n{context}\n\n"
            "{source_info}\n\n"
            "厳格な指示:\n"
            "1. レポートは包括的でプロフェッショナルであり、明確な見出しを伴う構造になっている必要があります。出力は日本語で作成してください。\n"
            "2. {citation_instruction}\n"
            "3. ソースがある場合、すべての主要な主張やデータポイントには引用を付けることが理想的です。\n"
            "4. 提供されたリストにないソースには言及しないでください。\n"
            "5. 最後に調査結果のまとめを記述してください。"
        ),
        "English": (
            "Synthesize a final research report for the topic: {topic}\n\n"
            "Research Context (Summaries from various sections):\n{context}\n\n"
            "{source_info}\n\n"
            "STRICT INSTRUCTIONS:\n"
            "1. The report must be comprehensive, professional, and well-structured with clear headings.\n"
            "2. {citation_instruction}\n"
            "3. Every major claim or data point should ideally be cited if sources are available.\n"
            "4. Do not mention sources that are not in the provided list.\n"
            "5. End with a summary of the findings."
        )
    },
    "follow_up_prompt": {
        "Japanese": (
            "以下のリサーチレポートに基づいて、ユーザーのフォローアップ質問に答えてください。\n\n"
            "レポート:\n{report}\n\n"
            "ユーザーの質問: {question}\n\n"
            "レポートの内容のみに基づいて、明確で簡潔な回答を提供してください。回答は日本語で行ってください。"
        ),
        "English": (
            "Based on the following research report, answer the user's follow-up question.\n\n"
            "Report:\n{report}\n\n"
            "User Question: {question}\n\n"
            "Provide a clear and concise answer based only on the report content."
        )
    }
}
