from deep_research_project.core.utils import sanitize_query

def test():
    print("Testing OpenAI-style string input...")
    input_str = "  **Latest AI Trends 2024**  "
    result_str = sanitize_query(input_str)
    print(f"Result: '{result_str}' (Expected: 'Latest AI Trends 2024')")
    
    print("\nTesting Gemini-style list input...")
    input_list = ["Next", "gen", "LLM", "2025"]
    result_list = sanitize_query(input_list)
    print(f"Result: '{result_list}' (Expected: 'Next gen LLM 2025')")

    print("\nTesting multi-line string input...")
    input_multiline = "Query 1\nQuery 2"
    result_multiline = sanitize_query(input_multiline)
    print(f"Result: '{result_multiline}' (Expected: 'Query 1')")

if __name__ == "__main__":
    test()
