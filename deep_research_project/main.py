import os
import sys
import argparse

# Adjust path to import from sibling directories
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv()

from deep_research_project.config.config import Configuration
from deep_research_project.core.state import ResearchState
from deep_research_project.core.research_loop import ResearchLoop
import logging
import asyncio

async def main():
    parser = argparse.ArgumentParser(description="AI Research Assistant CLI")
    parser.add_argument("topic", nargs="?", default="Modern AI Research Agents", help="Research topic")
    parser.add_argument("-i", "--interactive", action="store_true", help="Run in interactive mode")
    parser.add_argument("-l", "--loops", type=int, help="Max research loops")
    parser.add_argument("-r", "--results", type=int, help="Max search results per query")
    parser.add_argument("-s", "--snippets", action="store_true", help="Use snippets only mode")
    parser.add_argument("--chunk-size", type=int, help="Summarization chunk size (chars)")
    parser.add_argument("--chunk-overlap", type=int, help="Summarization chunk overlap (chars)")
    parser.add_argument("--lang", choices=["Japanese", "English"], default="Japanese", help="Prompt language")
    args = parser.parse_args()

    try:
        config = Configuration()
        # Override config with CLI arguments
        if args.interactive:
            config.INTERACTIVE_MODE = True
        else:
            config.INTERACTIVE_MODE = False # Default to False for CLI unless specified

        if args.loops is not None:
            config.MAX_RESEARCH_LOOPS = args.loops
        if args.results is not None:
            config.MAX_SEARCH_RESULTS_PER_QUERY = args.results
        if args.snippets:
            config.USE_SNIPPETS_ONLY_MODE = True
        if args.chunk_size is not None:
            config.SUMMARIZATION_CHUNK_SIZE_CHARS = args.chunk_size
        if args.chunk_overlap is not None:
            config.SUMMARIZATION_CHUNK_OVERLAP_CHARS = args.chunk_overlap

    except Exception as e:
        print(f"CRITICAL: Error initializing configuration: {e}")
        return

    log_format = '%(asctime)s - %(levelname)s - %(name)s - %(module)s.%(funcName)s:%(lineno)d - %(message)s'
    logging.basicConfig(level=config.LOG_LEVEL, format=log_format)
    logger = logging.getLogger(__name__)

    research_topic = args.topic
    state = ResearchState(research_topic=research_topic, language=args.lang)
    research_runner = ResearchLoop(config=config, state=state)

    logger.info(f"Starting the research process for: {research_topic} (Interactive: {config.INTERACTIVE_MODE})")
    try:
        final_report = await research_runner.run_loop()
        if final_report:
            print("\n========== FINAL REPORT ==========")
            print(final_report)
            output_filename = config.OUTPUT_FILENAME
            with open(output_filename, "w", encoding="utf-8") as f:
                f.write(final_report)
            logger.info(f"Report saved to: {output_filename}")
        else:
            if config.INTERACTIVE_MODE:
                print("\nResearch paused for user input. Please use a UI for interactive mode or run in automated mode.")
    except Exception as e:
        logger.error(f"An error occurred: {e}", exc_info=True)

if __name__ == "__main__":
    asyncio.run(main())
