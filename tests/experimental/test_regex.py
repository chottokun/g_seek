import re

def extract(report):
    json_pattern = r"```json\s*\n(.*?)\n?```"
    json_matches = re.findall(json_pattern, report, re.DOTALL)
    if not json_matches:
        raw_json_match = re.search(r"(\{\s*\"nodes\":.*?\})", report, re.DOTALL | re.IGNORECASE)
        if raw_json_match:
            json_matches = [raw_json_match.group(1)]
    return json_matches

test_cases = [
    ("Old format\n```json\n{\"nodes\": []}\n```\nEnd", "Standard Block"),
    ("Missing newline\n```json\n{\"nodes\": []}```\nEnd", "Missing Newline"),
    ("No code block\nJust raw data: {\"nodes\": [{\"id\": 1}]} in middle", "Raw Fallback"),
    ("Casing\n```JSON\n{\"nodes\": []}\n```", "Case Sensitivity (if applicable)"),
]

for report, label in test_cases:
    found = extract(report)
    print(f"Case: {label} -> {'Found' if found else 'NOT FOUND'}")
    if found:
        print(f"  Content: {found[0][:50]}")
