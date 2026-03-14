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
    # Load config and override some values for testing
    config = Configuration()
    config.INTERACTIVE_MODE = False
    config.MAX_RESEARCH_LOOPS = 2
    config.RESEARCH_PLAN_MAX_SECTIONS = 3
    
    print(f"Provider: {config.LLM_PROVIDER}, Model: {config.LLM_MODEL}")
    
    state = ResearchState(research_topic="令和の米騒動（2024-2025年）の原因と影響、政府の対策状況", language="Japanese")
    loop = ResearchLoop(config, state, progress_callback=mock_progress_callback)
    
    print("Starting Research Loop in CLI Mode (Japanese)...")
    try:
        report = await loop.run_loop()
        print("\n" + "="*50)
        print("Research Complete!")
        print("Final Report Length:", len(report) if report else 0)
        print("="*50)
        
        if report:
            print("\n--- REPORT PREVIEW ---")
            print(report[:2000] + "...")
            
            # Save to a temp file for inspection
            with open("test_cli_report.md", "w", encoding="utf-8") as f:
                f.write(report)
            print(f"\nFull report saved to: {os.path.abspath('test_cli_report.md')}")
            
    except Exception as e:
        print(f"Research failed: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(main())
