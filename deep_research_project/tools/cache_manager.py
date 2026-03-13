import os
import json
import hashlib
import aiofiles
import logging
import time
from typing import Optional, Any
from pathlib import Path

logger = logging.getLogger(__name__)

class CacheManager:
    def __init__(self, cache_dir: str = ".cache", enabled: bool = True):
        self.cache_dir = Path(cache_dir)
        self.enabled = enabled
        if self.enabled:
            self.cache_dir.mkdir(parents=True, exist_ok=True)
            (self.cache_dir / "llm").mkdir(exist_ok=True)
            (self.cache_dir / "content").mkdir(exist_ok=True)

    def _get_hash(self, key: str) -> str:
        return hashlib.md5(key.encode("utf-8")).hexdigest()

    async def get_llm_cache(self, prompt: str) -> Optional[str]:
        if not self.enabled:
            return None
        
        cache_file = self.cache_dir / "llm" / f"{self._get_hash(prompt)}.json"
        if cache_file.exists():
            try:
                async with aiofiles.open(cache_file, mode="r", encoding="utf-8") as f:
                    data = json.loads(await f.read())
                    timestamp = data.get("timestamp", 0)
                    # 12 hours TTL = 43200 seconds
                    if time.time() - timestamp < 43200:
                        return data.get("response")
                    else:
                        logger.debug("LLM cache expired (TTL > 12h).")
            except Exception as e:
                logger.warning(f"Failed to read LLM cache: {e}")
        return None

    async def set_llm_cache(self, prompt: str, response: str):
        if not self.enabled:
            return
        
        cache_file = self.cache_dir / "llm" / f"{self._get_hash(prompt)}.json"
        try:
            async with aiofiles.open(cache_file, mode="w", encoding="utf-8") as f:
                await f.write(json.dumps({
                    "prompt": prompt, 
                    "response": response,
                    "timestamp": time.time()
                }, ensure_ascii=False))
        except Exception as e:
            logger.warning(f"Failed to write LLM cache: {e}")

    async def get_content_cache(self, url: str) -> Optional[str]:
        if not self.enabled:
            return None
        
        cache_file = self.cache_dir / "content" / f"{self._get_hash(url)}.json"
        if cache_file.exists():
            try:
                async with aiofiles.open(cache_file, mode="r", encoding="utf-8") as f:
                    data = json.loads(await f.read())
                    return data.get("content")
            except Exception as e:
                logger.warning(f"Failed to read content cache: {e}")
        return None

    async def set_content_cache(self, url: str, content: str):
        if not self.enabled:
            return
        
        cache_file = self.cache_dir / "content" / f"{self._get_hash(url)}.json"
        try:
            async with aiofiles.open(cache_file, mode="w", encoding="utf-8") as f:
                await f.write(json.dumps({"url": url, "content": content}, ensure_ascii=False))
        except Exception as e:
            logger.warning(f"Failed to write content cache: {e}")
