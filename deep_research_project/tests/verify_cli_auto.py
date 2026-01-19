import asyncio
import os
import sys

# Add project root to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from deep_research_project.config.config import Configuration
from deep_research_project.core.state import ResearchState
from deep_research_project.core.research_loop import ResearchLoop

async def mock_progress_callback(info: str):
    print(f"[PROGRESS] {info}")

async def main():
    print("Initializing Configuration...")
    config = Configuration()
    print(f"Interactive Mode: {config.INTERACTIVE_MODE}")
    
    if config.INTERACTIVE_MODE:
        print("ERROR: Interactive Mode should be False by default now.")
        # We allow it to proceed but note the error, or force it for the test if it failed
        # But the goal is to test the default
    
    # Force it just in case we want to test the loop logic specifically regardless of config file state (though config file state is what we are testing too)
    # But let's trust the config loaded from file/env.
    
    state = ResearchState(research_topic="Quantum Computing Trends 2025", language="English")
    loop = ResearchLoop(config, state, progress_callback=mock_progress_callback)
    
    print("Starting Research Loop in Automatic Mode...")
    try:
        report = await loop.run_loop()
        print("\nResearch Complete!")
        print("Final Report Length:", len(report) if report else 0)
    except Exception as e:
        print(f"Research failed: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(main())
