import os
from .config.config import Configuration
from .core.state import ResearchState
from .core.research_loop import ResearchLoop
import logging

# Logger for this module (main.py) will be configured in main()
# but other modules will use their own loggers configured by basicConfig.

def main():
    # Initialize Configuration first, as it contains LOG_LEVEL
    try:
        config = Configuration()
    except ValueError as e:
        # Cannot use logger yet if config fails at the very start (e.g. LOG_LEVEL itself is bad)
        print(f"CRITICAL: Error initializing configuration: {e}. Cannot start application.")
        print("Ensure environment variables are set correctly or .env file is valid.")
        return
    except Exception as e:
        print(f"CRITICAL: An unexpected error occurred during configuration: {e}. Cannot start application.")
        return

    # Set up logging as early as possible
    log_format = '%(asctime)s - %(levelname)s - %(name)s - %(module)s.%(funcName)s:%(lineno)d - %(message)s'
    logging.basicConfig(level=config.LOG_LEVEL, format=log_format)

    logger = logging.getLogger(__name__) # Get logger for this module (main)

    logger.info("Starting Deep Research Application...")
    logger.info("Configuration loaded:")
    logger.info(f"  LLM Provider: {config.LLM_PROVIDER}")
    logger.info(f"  Search API: {config.SEARCH_API}")
    logger.info(f"  Max Loops: {config.MAX_RESEARCH_LOOPS}")
    logger.info(f"  Log Level: {config.LOG_LEVEL}")


    # 2. Initialize Research State
    # TODO: Later, this topic could come from user input (e.g., command line argument or Streamlit UI)
    research_topic = "The Role of Artificial Intelligence in Personalized Medicine"
    state = ResearchState(research_topic=research_topic)
    logger.info(f"Research topic: {state.research_topic}")

    # 3. Initialize Research Loop
    try:
        research_runner = ResearchLoop(config=config, state=state)
    except Exception as e:
        logger.error(f"Error initializing research loop: {e}", exc_info=True)
        return

    # 4. Run the loop
    logger.info("Starting the research process...")
    try:
        final_report = research_runner.run_loop()
    except Exception as e:
        logger.error(f"An error occurred during the research process: {e}", exc_info=True)
        # No need for traceback.print_exc() as logger.error with exc_info=True does this
        return

    # 5. Output the final report
    if final_report:
        logger.info("\n========== FINAL REPORT ==========")
        # Log potentially large report content at DEBUG level or chunk it for INFO
        if len(final_report) < 1000: # Arbitrary limit for INFO level
            logger.info(final_report)
        else:
            logger.info("Final report generated (content logged at DEBUG level due to size).")
            logger.debug(f"Full Final Report:\n{final_report}")
        logger.info("================================")

        # Optionally, save the report to a file
        output_filename = config.OUTPUT_FILENAME
        try:
            with open(output_filename, "w", encoding="utf-8") as f:
                f.write(final_report)
            logger.info(f"Report successfully saved to: {output_filename}")
        except IOError as e:
            logger.error(f"Error saving report to file {output_filename}: {e}", exc_info=True)
    else:
        logger.warning("No final report was generated.")

    logger.info("Deep Research Application Finished.")

if __name__ == "__main__":
    # This initial .env creation logic runs before logging is configured by main().
    # So, it uses print for this specific, one-time setup message.
    # The .env file should exist in the root of the project, so /app/.env
    # When running `python -m deep_research_project.main`, CWD is /app.
    env_file_path = ".env"
    if not os.path.exists(env_file_path):
        print(f"Creating a dummy .env file at '{os.path.abspath(env_file_path)}' as it was not found (for placeholder run).")
        try:
            with open(env_file_path, "w") as f:
                f.write("# This is a dummy .env file for placeholder runs\n")
                f.write("LLM_PROVIDER=placeholder_llm\n")
                f.write("SEARCH_API=duckduckgo\n")
                f.write(f"LOG_LEVEL=INFO\n") # Add default log level
        except IOError as e:
            print(f"Failed to create dummy .env file: {e}")
            # Application might still run if defaults in config.py are sufficient
            # and no sensitive keys are strictly required by chosen providers.

    main()
