from typing import List

def split_text_into_chunks(text: str, chunk_size: int, chunk_overlap: int) -> List[str]:
    """Splits a given text into overlapping chunks."""
    if not text: return []
    if chunk_size <= 0: raise ValueError("Chunk size must be positive.")
    if chunk_overlap < 0 or chunk_overlap >= chunk_size:
        raise ValueError("Invalid chunk overlap.")

    text_len = len(text)
    if text_len <= chunk_size: return [text]

    chunks = []
    idx = 0
    while idx < text_len:
        end_idx = idx + chunk_size
        chunks.append(text[idx:end_idx])
        if end_idx >= text_len: break
        idx += (chunk_size - chunk_overlap)
    return chunks
