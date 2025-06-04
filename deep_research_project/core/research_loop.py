from ..config.config import Configuration
from .state import ResearchState, SearchResult, Source # Adjusted import path

# Placeholder for LLM and Search Tool clients (to be implemented in Step 5)
from ..tools.llm_client import LLMClient # Example
from ..tools.search_client import SearchClient # Example
import logging

logger = logging.getLogger(__name__)

class ResearchLoop:
    def __init__(self, config: Configuration, state: ResearchState):
        self.config = config
        self.state = state
        logger.info("Initializing LLM and Search clients for ResearchLoop.")
        try:
            self.llm_client = LLMClient(config)
            self.search_client = SearchClient(config)
            logger.info("ResearchLoop initialized successfully.")
            logger.info(f"Configuration: LLM Provider={self.config.LLM_PROVIDER}, Search API={self.config.SEARCH_API}")
            logger.info(f"Initial State: Research Topic='{self.state.research_topic}'")
        except Exception as e:
            logger.error(f"Error during ResearchLoop initialization: {e}", exc_info=True)
            raise # Re-raise the exception to be caught by the caller


    def _generate_initial_query(self):
        logger.info(f"Generating initial query for topic: {self.state.research_topic}")
        try:
            query_prompt = f"Generate a concise search query for the topic: {self.state.research_topic}"
            query = self.llm_client.generate_text(prompt=query_prompt)
        # query = f"Initial search query for {self.state.research_topic}" # Placeholder
            self.state.initial_query = query
            self.state.current_query = query
            logger.info(f"Initial query generated: {self.state.initial_query}")
        except Exception as e:
            logger.error(f"Error generating initial query: {e}", exc_info=True)
            self.state.current_query = None # Stop loop if query generation fails


    def _web_search(self):
        logger.debug(f"Entering _web_search for query: {self.state.current_query}")
        if not self.state.current_query:
            logger.warning("No current query to search. Skipping web search.")
            self.state.search_results = [] # Ensure it's an empty list
            return

        logger.info(f"Performing web search for: {self.state.current_query}")
        try:
            search_results_raw = self.search_client.search(self.state.current_query, num_results=self.config.MAX_SEARCH_RESULTS_PER_QUERY)
        # Ensure search_results_raw is a list of SearchResult compatible dicts
            self.state.search_results = [
                SearchResult(title=r['title'], link=r['link'], snippet=r['snippet'])
                for r in search_results_raw
            ]

            logger.info(f"Found {len(self.state.search_results)} results.")
            for i, res in enumerate(self.state.search_results):
                logger.debug(f"  Result {i+1}: {res['title']} ({res['link']})")
        except Exception as e:
            logger.error(f"Error during web search for query '{self.state.current_query}': {e}", exc_info=True)
            self.state.search_results = []


    def _summarize_sources(self):
        logger.debug("Entering _summarize_sources.")
        if not self.state.search_results: # Check if list is empty or None
            logger.info("No search results to summarize.")
            self.state.new_information = None
            return

        logger.info("Summarizing search results...")
        try:
            valid_results = [res for res in self.state.search_results if res.get('snippet')]
            if not valid_results:
                logger.warning("No search results with snippets to summarize.")
                self.state.new_information = "No new information with snippets found to summarize." # Set a message
                # Still add sources that might have titles/links even without snippets
                for res in self.state.search_results:
                    if res['link'] not in [s['link'] for s in self.state.sources_gathered]:
                        self.state.sources_gathered.append(Source(title=res['title'], link=res['link']))
                return

            combined_text = "\n".join([f"Title: {r['title']}\nLink: {r['link']}\nSnippet: {r['snippet']}" for r in valid_results])
            summary_prompt = f"Summarize the following information relevant to the query '{self.state.current_query}':\n{combined_text}"
            new_summary = self.llm_client.generate_text(prompt=summary_prompt)

        #new_summary = f"This is a summary of new information found for query '{self.state.current_query}'." # Placeholder
            self.state.new_information = new_summary
            self.state.accumulated_summary += f"\n\n## Findings for query: {self.state.current_query}\n{new_summary}"

        # Update sources gathered
            for res in self.state.search_results: # Log all sources found in search, even if snippet was empty for summary
                if res['link'] not in [s['link'] for s in self.state.sources_gathered]:
                    self.state.sources_gathered.append(Source(title=res['title'], link=res['link']))

            logger.info(f"New information summary generated (length: {len(self.state.new_information) if self.state.new_information else 0}).")
            logger.debug(f"Accumulated summary length: {len(self.state.accumulated_summary)}")
        except Exception as e:
            logger.error(f"Error summarizing sources for query '{self.state.current_query}': {e}", exc_info=True)
            self.state.new_information = "Error occurred during summary generation."


    def _reflect_on_summary(self):
        logger.debug("Entering _reflect_on_summary.")
        logger.info("Reflecting on summary and generating next query...")
        try:
            reflection_prompt = (
               f"Current research topic: {self.state.research_topic}\n"
               f"Accumulated summary so far:\n{self.state.accumulated_summary}\n\n"
               f"Based on the summary, identify key knowledge gaps or areas that need further investigation. "
               f"Generate a new, specific search query to address these gaps. If the topic seems well-covered, output 'None'. "
               f"This is for loop {self.state.completed_loops + 1} of {self.config.MAX_RESEARCH_LOOPS}." # Corrected placeholder text
            )
            next_query = self.llm_client.generate_text(prompt=reflection_prompt)

        # Placeholder logic
        # if self.state.completed_loops < self.config.MAX_RESEARCH_LOOPS -1 : # Subtract 1 because completed_loops is 0-indexed for the first loop
        #     next_query = f"Refined query based on loop {self.state.completed_loops + 1} for {self.state.research_topic}"
        # else:
        #     next_query = "None" # End condition for placeholder

            if next_query.strip().lower() == "none":
                self.state.current_query = None
                logger.info("Reflection: No further queries needed.")
            else:
                self.state.current_query = next_query
                logger.info(f"Next query: {self.state.current_query}")
        except Exception as e:
            logger.error(f"Error during reflection and next query generation: {e}", exc_info=True)
            self.state.current_query = None # Stop loop on error


    def _finalize_summary(self):
        logger.debug("Entering _finalize_summary.")
        logger.info("Finalizing summary...")
        report_parts = [f"# Research Report: {self.state.research_topic}\n"]
        report_parts.append("## Accumulated Findings") # Removed \n, added later
        if self.state.accumulated_summary.strip(): # Add summary only if it's not empty
            report_parts.append(self.state.accumulated_summary.strip())
        else:
            report_parts.append("No information was gathered during the research process.")

        if self.state.sources_gathered:
            report_parts.append("\n\n## Sources") # Removed \n, added later
            for i, source in enumerate(self.state.sources_gathered):
                report_parts.append(f"\n{i+1}. {source['title']} ({source['link']})") # Added \n before each source

        self.state.final_report = "\n".join(report_parts)
        logger.info("Final report generated.")
        logger.debug(f"Final Report Content (first 200 chars):\n{self.state.final_report[:200]}...")


    def run_loop(self):
        logger.info(f"Starting research loop for topic: '{self.state.research_topic}'")

        self._generate_initial_query()

        while self.state.completed_loops < self.config.MAX_RESEARCH_LOOPS and self.state.current_query:
            logger.info(f"--- Starting Loop {self.state.completed_loops + 1} of {self.config.MAX_RESEARCH_LOOPS} ---")
            self._web_search()
            self._summarize_sources()
            self.state.completed_loops += 1
            if self.state.completed_loops < self.config.MAX_RESEARCH_LOOPS and self.state.current_query: # check current_query again
                 self._reflect_on_summary()
            elif self.state.current_query is None: # Query was set to None by a failing step or reflection
                logger.info("Current query is None, terminating loop early.")
            else: # Max loops reached
                logger.info(f"Max research loops ({self.config.MAX_RESEARCH_LOOPS}) reached.")
                self.state.current_query = None # Ensure loop terminates

        self._finalize_summary()
        logger.info("Research loop finished.")
        return self.state.final_report


# Example usage (optional, for testing this module directly)
if __name__ == "__main__":
    # This example won't run correctly until LLMClient and SearchClient are implemented
    # and Configuration can be instantiated without error (e.g. API keys might be needed)
    # Basic logging for example usage
    logging.basicConfig(level=logging.DEBUG,
                        format='%(asctime)s - %(levelname)s - %(name)s - %(module)s.%(funcName)s:%(lineno)d - %(message)s')
    logger.info("Running research_loop.py example...")
    try:
        # Create a dummy .env file for this example if OPENAI_API_KEY is needed by Configuration
        # with open("../.env", "w") as f:
        # f.write("OPENAI_API_KEY=test_key\n") # Example, adjust if your config needs other keys

        # Default config will use placeholders if no .env is present and defaults are set for providers
        test_config = Configuration()
        test_config.MAX_RESEARCH_LOOPS = 2 # For quicker testing
        # test_config.LOG_LEVEL = "DEBUG" # This should be handled by the Configuration loading .env or default
        # If a specific level is needed for this test, it should be set after Configuration instantiation
        # or by ensuring basicConfig is called after test_config is loaded.
        # Re-applying basicConfig here if needed:
        # logging.getLogger().setLevel(test_config.LOG_LEVEL) # More dynamic if basicConfig already called

        test_state = ResearchState(research_topic="Future of Renewable Energy")

        loop_runner = ResearchLoop(config=test_config, state=test_state)
        final_report = loop_runner.run_loop()

        if final_report:
            logger.info("\n--- Generated Report (Example Usage) ---") # Use logger
            logger.info(final_report) # Use logger
            logger.info("\n--- End of Report (Example Usage) ---") # Use logger
        else:
            logger.warning("No report was generated in example usage.") # Use logger

    except Exception as e:
        logger.error(f"Error in research_loop.py example usage: {e}", exc_info=True) # Use logger
# No traceback import needed if exc_info=True is used with logger.error
