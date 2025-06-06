from deep_research_project.config.config import Configuration
from .state import ResearchState, SearchResult, Source # Adjusted import path

# Placeholder for LLM and Search Tool clients (to be implemented in Step 5)
from deep_research_project.tools.llm_client import LLMClient # Example
from deep_research_project.tools.search_client import SearchClient # Example
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
            # LLMに検索クエリのみを生成させるための厳密なプロンプト
            query_prompt = (
                f"Based on the following research topic, generate a concise search query suitable for a web search engine.\n"
                f"Research Topic: {self.state.research_topic}\n\n"
                f"Output only the search query itself, nothing else. "
                f"The query should be concise and specific, ideally no more than 12 words."
            )
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
        logger.info("Reflecting on summary, evaluating research direction, and generating next query...")
        try:
            reflection_prompt = (
                f"Current research topic: {self.state.research_topic}\n"
                f"Accumulated summary so far:\n{self.state.accumulated_summary}\n\n"
                f"Instructions:\n"
                f"1. Evaluate the current research direction. Available evaluations are: CONTINUE, MODIFY_TOPIC, CONCLUDE.\n"
                f"2. Identify key knowledge gaps or areas that need further investigation based on the summary.\n"
                f"3. Suggest a new, specific search query (max 12 words) to address these gaps. If evaluation is CONCLUDE, the query should be 'None'.\n"
                f"4. If the topic seems well-covered or further investigation is unproductive, evaluate as CONCLUDE.\n"
                f"5. Format your response exactly as follows:\n"
                f"EVALUATION: <CONTINUE|MODIFY_TOPIC|CONCLUDE>\n"
                f"QUERY: <Your new search query or None>\n\n"
                f"This is for reflection cycle {self.state.completed_loops + 1} of {self.config.MAX_RESEARCH_LOOPS}."
            )

            llm_response = self.llm_client.generate_text(prompt=reflection_prompt)
            logger.debug(f"LLM reflection response:\n{llm_response}")

            # Parse LLM response
            evaluation = "ERROR" # Default in case of parsing failure
            next_query = None

            try:
                lines = llm_response.strip().split('\n')
                for line in lines:
                    if line.startswith("EVALUATION:"):
                        evaluation = line.split(":", 1)[1].strip().upper()
                    elif line.startswith("QUERY:"):
                        next_query_str = line.split(":", 1)[1].strip()
                        if next_query_str.lower() != "none":
                            next_query = next_query_str
            except Exception as parse_error:
                logger.error(f"Error parsing LLM reflection response: {parse_error}. Response was:\n{llm_response}", exc_info=True)
                # Keep evaluation as "ERROR" and next_query as None

            logger.info(f"Reflection - Evaluation: {evaluation}, Next Query: '{next_query}'")

            if evaluation == "CONCLUDE":
                logger.info("Reflection evaluation is CONCLUDE. Terminating research loop.")
                self.state.current_query = None
            elif evaluation == "MODIFY_TOPIC":
                logger.info("Reflection evaluation is MODIFY_TOPIC. Current query will be updated. Deeper topic modification is out of scope for now.")
                if next_query:
                    self.state.current_query = f"Refined Topic Query: {next_query}" # Simplified handling
                    logger.info(f"New query based on topic modification suggestion: {self.state.current_query}")
                else:
                    logger.warning("MODIFY_TOPIC suggested, but no new query provided by LLM. Concluding research.")
                    self.state.current_query = None
            elif evaluation == "CONTINUE":
                if next_query:
                    self.state.current_query = next_query
                    logger.info(f"Continuing with new query: {self.state.current_query}")
                else:
                    logger.info("Reflection evaluation is CONTINUE, but no next query provided. Terminating research loop.")
                    self.state.current_query = None
            else: # Handles "ERROR" or any unexpected evaluation
                logger.warning(f"Reflection evaluation was '{evaluation}'. Terminating research due to unclear direction or error.")
                self.state.current_query = None

        except Exception as e:
            logger.error(f"Error during reflection and next query generation: {e}", exc_info=True)
            self.state.current_query = None # Stop loop on error


    def _finalize_summary(self):
        logger.debug("Entering _finalize_summary.")
        logger.info("Finalizing summary...")

        if not self.state.accumulated_summary or self.state.accumulated_summary.isspace():
            logger.info("Accumulated summary is empty. Reporting no information gathered.")
            report_content = (
                f"# Research Report: {self.state.research_topic}\n\n"
                "No information was gathered during the research process."
            )
        else:
            logger.info("Accumulated summary has content. Generating final report with LLM.")
            prompt = (
                f"Research Topic: {self.state.research_topic}\n\n"
                f"Accumulated Information:\n{self.state.accumulated_summary}\n\n"
                f"Task: Based on the research topic and the accumulated information, synthesize a comprehensive and detailed report. "
                f"Ensure all key findings are included, the report is well-organized, and it is presented in a professional tone. "
                f"The report should be a narrative synthesis of the information, not just a list of summaries."
            )
            try:
                llm_generated_report = self.llm_client.generate_text(prompt=prompt)
                report_content = f"# Research Report: {self.state.research_topic}\n\n{llm_generated_report}"
                logger.info("LLM generated the final report content.")
            except Exception as e:
                logger.error(f"Error during LLM call for final report generation: {e}", exc_info=True)
                report_content = (
                    f"# Research Report: {self.state.research_topic}\n\n"
                    "## Accumulated Findings\n"
                    f"{self.state.accumulated_summary.strip()}\n\n"
                    "## Error\n"
                    "An error occurred while generating the final synthesized report with the LLM. "
                    "The above are the raw accumulated findings."
                )

        # Append sources
        sources_section = ""
        if self.state.sources_gathered:
            sources_list = []
            for i, source in enumerate(self.state.sources_gathered):
                sources_list.append(f"{i+1}. {source['title']} ({source['link']})")
            sources_section = "\n\n## Sources\n" + "\n".join(sources_list)

        self.state.final_report = report_content + sources_section
        logger.info("Final report constructed.")
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
