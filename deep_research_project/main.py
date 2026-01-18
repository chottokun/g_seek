import os
from dotenv import load_dotenv
load_dotenv()

from deep_research_project.config.config import Configuration
from deep_research_project.core.state import ResearchState
from deep_research_project.core.research_loop import ResearchLoop
import logging
import asyncio

async def main():
    os.environ["INTERACTIVE_MODE"] = "False"
    try:
        config = Configuration()
    except Exception as e:
        print(f"CRITICAL: Error initializing configuration: {e}")
        return

    log_format = '%(asctime)s - %(levelname)s - %(name)s - %(module)s.%(funcName)s:%(lineno)d - %(message)s'
    logging.basicConfig(level=config.LOG_LEVEL, format=log_format)
    logger = logging.getLogger(__name__)

    research_topic = "Modern AI Research Agents"
    state = ResearchState(research_topic=research_topic)
    research_runner = ResearchLoop(config=config, state=state)

    logger.info("Starting the research process (Async)...")
    try:
        final_report = await research_runner.run_loop()
        if final_report:
            print("\n========== FINAL REPORT ==========")
            print(final_report)
            output_filename = config.OUTPUT_FILENAME
            with open(output_filename, "w", encoding="utf-8") as f:
                f.write(final_report)
            logger.info(f"Report saved to: {output_filename}")
    except Exception as e:
        logger.error(f"An error occurred: {e}", exc_info=True)

if __name__ == "__main__":
    asyncio.run(main())
