from typing import List

def split_text_into_chunks(text: str, chunk_size: int, chunk_overlap: int) -> List[str]:
    """Splits a given text into overlapping chunks."""
    if not text: return []
    if chunk_size <= 0: return [text]
    
    if chunk_overlap >= chunk_size:
        # Fallback to avoid infinite loop or unexpected behavior
        # Though the config validator handles this, we add a safety check here
        chunk_overlap = chunk_size // 2

    chunks = []
    start = 0
    while start < len(text):
        end = start + chunk_size
        chunks.append(text[start:end])
        if end >= len(text):
            break
        start += (chunk_size - chunk_overlap)
    return chunks

def sanitize_query(query: str) -> str:
    """Cleans and truncates the query to prevent API errors."""
    if not query: return ""
    # Remove markdown bold/italic/code fences
    clean = query.strip().replace("**", "").replace("__", "").replace("`", "").replace('"', '')
    # Take only the first line if multiple lines returned
    clean = clean.split('\n')[0].strip()
    # Truncate to a reasonable character length (e.g., 100 characters)
    if len(clean) > 100:
        # Try to cut at word boundary
        parts = clean[:100].rsplit(' ', 1)
        if len(parts) > 1:
            clean = parts[0]
        else:
            clean = clean[:100]
    return clean
