import asyncio
import unittest
import os
import shutil
from pathlib import Path
from deep_research_project.tools.cache_manager import CacheManager

class TestCacheManager(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.test_cache_dir = ".test_cache"
        self.cache = CacheManager(cache_dir=self.test_cache_dir, enabled=True)

    async def asyncTearDown(self):
        if os.path.exists(self.test_cache_dir):
            shutil.rmtree(self.test_cache_dir)

    async def test_llm_cache(self):
        prompt = "Hello, world!"
        response = "Hi there!"
        
        # Initially empty
        self.assertIsNone(await self.cache.get_llm_cache(prompt))
        
        # Set and get
        await self.cache.set_llm_cache(prompt, response)
        self.assertEqual(await self.cache.get_llm_cache(prompt), response)
        
        # Persistent check (new manager instance)
        cache2 = CacheManager(cache_dir=self.test_cache_dir, enabled=True)
        self.assertEqual(await cache2.get_llm_cache(prompt), response)

    async def test_content_cache(self):
        url = "https://example.com"
        content = "Example content"
        
        await self.cache.set_content_cache(url, content)
        self.assertEqual(await self.cache.get_content_cache(url), content)

if __name__ == "__main__":
    unittest.main()
