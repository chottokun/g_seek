import asyncio
import time
import os
import shutil
from pathlib import Path
from deep_research_project.core.skills_manager import SkillRegistry

async def background_task():
    """A background task that should run smoothly."""
    delays = []
    start = time.perf_counter()
    while time.perf_counter() - start < 1.0:
        t0 = time.perf_counter()
        await asyncio.sleep(0.005)
        t1 = time.perf_counter()
        delays.append(t1 - t0)
    return delays

async def benchmark_save_skill():
    skills_dir = "test_skills_bench"
    if os.path.exists(skills_dir):
        shutil.rmtree(skills_dir)

    registry = SkillRegistry(skills_dir=skills_dir)

    # Simulate some work
    content = "A" * 10 * 1024 * 1024 # 10MB of content

    bg_task = asyncio.create_task(background_task())

    await asyncio.sleep(0.2) # Let bg task start

    start_time = time.perf_counter()
    if asyncio.iscoroutinefunction(registry.save_skill):
        await registry.save_skill("test-skill", "Test Skill", "Description", content)
    else:
        registry.save_skill("test-skill", "Test Skill", "Description", content)
    end_time = time.perf_counter()

    save_duration = end_time - start_time
    print(f"save_skill took: {save_duration:.4f} seconds")

    delays = await bg_task
    max_delay = max(delays) if delays else 0
    avg_delay = sum(delays) / len(delays) if delays else 0
    print(f"Max background task delay: {max_delay:.4f} seconds")
    print(f"Avg background task delay: {avg_delay:.4f} seconds")

    if os.path.exists(skills_dir):
        shutil.rmtree(skills_dir)

if __name__ == "__main__":
    asyncio.run(benchmark_save_skill())
