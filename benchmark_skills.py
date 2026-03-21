import asyncio
import time

async def background_task():
    """A background task that should run smoothly."""
    delays = []
    start = time.perf_counter()
    while time.perf_counter() - start < 1.0:
        t0 = time.perf_counter()
        await asyncio.sleep(0.005)
        t1 = time.perf_counter()
