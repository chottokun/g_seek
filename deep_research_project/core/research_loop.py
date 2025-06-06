from deep_research_project.config.config import Configuration
from .state import ResearchState, SearchResult, Source # Adjusted import path

# Placeholder for LLM and Search Tool clients (to be implemented in Step 5)
from deep_research_project.tools.llm_client import LLMClient # Example
from deep_research_project.tools.search_client import SearchClient # Example
from deep_research_project.tools.content_retriever import ContentRetriever # Added import
import logging
import json # Added for knowledge graph extraction
from typing import List

logger = logging.getLogger(__name__)

class ResearchLoop:
    def __init__(self, config: Configuration, state: ResearchState):
        self.config = config
        self.state = state
        self.interactive_mode = config.INTERACTIVE_MODE  # Store interactive_mode
        logger.info(f"Initializing LLM and Search clients for ResearchLoop. Interactive mode: {self.interactive_mode}")
        try:
            self.llm_client = LLMClient(config)
            self.search_client = SearchClient(config)
            self.content_retriever = ContentRetriever() # Added content retriever
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
            self.state.initial_query = query # Keep initial_query for record
            self.state.proposed_query = query
            self.state.current_query = None # Explicitly set current_query to None until approved
            logger.info(f"Initial query proposed: {self.state.proposed_query}")
        except Exception as e:
            logger.error(f"Error generating initial query: {e}", exc_info=True)
            self.state.proposed_query = None
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

            if self.state.search_results:
                self.state.pending_source_selection = True
                logger.info(f"Found {len(self.state.search_results)} results. Pending source selection.")
                for i, res in enumerate(self.state.search_results):
                    logger.debug(f"  Result {i+1}: {res['title']} ({res['link']})")
            else:
                self.state.pending_source_selection = False
                logger.info("No results found from web search.")
        except Exception as e:
            logger.error(f"Error during web search for query '{self.state.current_query}': {e}", exc_info=True)
            self.state.search_results = []
            self.state.pending_source_selection = False


    def _summarize_sources(self, selected_results: List[SearchResult]):
        logger.debug("Entering _summarize_sources.")
        if not selected_results: # Check if list is empty or None
            logger.info("No selected results to summarize.")
            self.state.new_information = "No sources were selected for summarization."
            self.state.pending_source_selection = False # Ensure this is reset if no selection is summarized
            return

        logger.info(f"Attempting to fetch and summarize content for {len(selected_results)} selected search results...")

        if self.state.fetched_content is None:
            self.state.fetched_content = {}

        for result in selected_results:
            link = result['link']
            if link not in self.state.fetched_content or not self.state.fetched_content[link]: # Fetch if not already fetched or empty
                logger.info(f"Fetching full text for: {link}")
                full_text = self.content_retriever.retrieve_and_extract(link)
                if full_text:
                    self.state.fetched_content[link] = full_text
                    logger.debug(f"Successfully fetched text for {link} (length: {len(full_text)}).")
                else:
                    logger.warning(f"Failed to fetch full text for {link}. Using snippet as fallback.")
                    self.state.fetched_content[link] = result.get('snippet', '') # Use snippet or empty string

        texts_to_summarize = []
        for r in selected_results:
            content = self.state.fetched_content.get(r['link'])
            if content: # Only include if content (either full or snippet fallback) exists
                texts_to_summarize.append(f"Source URL: {r['link']}\nTitle: {r['title']}\nContent:\n{content}")

        if not texts_to_summarize:
            logger.warning("No content (neither fetched nor snippet) available for any selected sources.")
            self.state.new_information = "Could not retrieve or find content for any of the selected sources."
            # Still update sources_gathered as the user intended to select these
            for res in selected_results:
                if res['link'] not in [s['link'] for s in self.state.sources_gathered]:
                    self.state.sources_gathered.append(Source(title=res['title'], link=res['link']))
            self.state.pending_source_selection = False
            return

        combined_text = "\n\n---\n\n".join(texts_to_summarize)

        if len(combined_text) > 100000: # Configurable threshold might be better
            logger.warning(f"Combined text for summarization is very long: {len(combined_text)} chars. May exceed LLM context limit.")

        try:
            summary_prompt = f"Summarize the following information relevant to the query '{self.state.current_query}':\n{combined_text}"
            new_summary = self.llm_client.generate_text(prompt=summary_prompt)

            self.state.new_information = new_summary
            self.state.accumulated_summary += f"\n\n## Findings for query: {self.state.current_query}\n{new_summary}"

            # Update sources gathered from the selected results (already done if no content was found)
            for res in selected_results:
                if res['link'] not in [s['link'] for s in self.state.sources_gathered]:
                    self.state.sources_gathered.append(Source(title=res['title'], link=res['link']))

            logger.info(f"New information summary generated (length: {len(self.state.new_information) if self.state.new_information else 0}).")
            logger.debug(f"Accumulated summary length: {len(self.state.accumulated_summary)}")
        except Exception as e:
            logger.error(f"Error summarizing sources for query '{self.state.current_query}': {e}", exc_info=True)
            self.state.new_information = "Error occurred during summary generation."
        finally:
            self.state.pending_source_selection = False # Summarization attempt made, selection process is over

        # After generating new_information, extract entities and relations
        if self.state.new_information and "Error occurred during summary generation." not in self.state.new_information and "No sources were selected" not in self.state.new_information and "Could not retrieve or find content" not in self.state.new_information :
            self._extract_entities_and_relations()


    def _extract_entities_and_relations(self):
        logger.debug("Entering _extract_entities_and_relations.")
        if not self.state.new_information or self.state.new_information.strip() == "" or \
           "Error occurred during summary generation." in self.state.new_information or \
           "No sources were selected for summarization." == self.state.new_information.strip() or \
           "Could not retrieve or find content for any of the selected sources." == self.state.new_information.strip():
            logger.warning("No new information available or information indicates previous error/lack of content, skipping entity and relation extraction.")
            self.state.knowledge_graph_nodes = [] # Ensure it's empty if no info
            self.state.knowledge_graph_edges = []
            return

        logger.info("Extracting entities and relations from new information.")

        text_content = self.state.new_information

        prompt = (
            f"Based on the following text, identify key entities (people, organizations, concepts, locations) and their relationships.\n"
            f"Format the output as a single JSON object with two keys: \"nodes\" and \"edges\".\n"
            f"\"nodes\" should be a list of objects, each with \"id\" (unique string, e.g., entity_name_type_1), \"label\" (entity name), and \"type\" (e.g., \"Person\", \"Organization\", \"Concept\", \"Location\").\n"
            f"\"edges\" should be a list of objects, each with \"source\" (id of source node), \"target\" (id of target node), and \"label\" (relationship description).\n\n"
            f"Ensure all node IDs used in \"edges\" are defined in \"nodes\". Use concise and descriptive labels for relationships.\n"
            f"If no entities or relationships are found, return a JSON object with empty lists for \"nodes\" and \"edges\".\n\n"
            f"Text:\n"
            f"---\n"
            f"{text_content}\n"
            f"---\n\n"
            f"JSON Output:"
        )

        try:
            llm_response = self.llm_client.generate_text(prompt=prompt)
            logger.debug(f"LLM response for KG extraction:\n{llm_response}")

            # Attempt to find JSON within the response if the LLM includes extra text
            json_start_index = llm_response.find('{')
            json_end_index = llm_response.rfind('}') + 1

            if json_start_index == -1 or json_end_index == 0:
                logger.error("No JSON object found in LLM response for KG extraction.")
                parsed_json = {"nodes": [], "edges": []}
            else:
                json_string = llm_response[json_start_index:json_end_index]
                try:
                    parsed_json = json.loads(json_string)
                except json.JSONDecodeError as e:
                    logger.error(f"Failed to decode JSON from LLM response for KG: {e}. Response snippet: {json_string[:200]}...", exc_info=True)
                    parsed_json = {"nodes": [], "edges": []} # Fallback

            # Replace strategy for nodes and edges
            self.state.knowledge_graph_nodes = parsed_json.get('nodes', [])
            self.state.knowledge_graph_edges = parsed_json.get('edges', [])

            logger.info(f"Extracted {len(self.state.knowledge_graph_nodes)} nodes and {len(self.state.knowledge_graph_edges)} edges.")

        except Exception as e:
            logger.error(f"An unexpected error occurred during entity and relation extraction: {e}", exc_info=True)
            self.state.knowledge_graph_nodes = [] # Ensure consistent state on error
            self.state.knowledge_graph_edges = []


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
                self.state.proposed_query = None
                self.state.current_query = None
            elif evaluation == "MODIFY_TOPIC":
                logger.info("Reflection evaluation is MODIFY_TOPIC. A new query will be proposed.")
                if next_query:
                    self.state.proposed_query = f"Refined Topic Query: {next_query}" # Simplified handling
                    self.state.current_query = None # Ensure current_query is cleared until approval
                    logger.info(f"New query proposed based on topic modification: {self.state.proposed_query}")
                else:
                    logger.warning("MODIFY_TOPIC suggested, but no new query provided by LLM. Concluding research.")
                    self.state.proposed_query = None
                    self.state.current_query = None
            elif evaluation == "CONTINUE":
                if next_query:
                    self.state.proposed_query = next_query
                    self.state.current_query = None # Ensure current_query is cleared until approval
                    logger.info(f"Continuing with proposed query: {self.state.proposed_query}")
                else:
                    logger.info("Reflection evaluation is CONTINUE, but no next query provided. Terminating research loop.")
                    self.state.proposed_query = None
                    self.state.current_query = None
            else: # Handles "ERROR" or any unexpected evaluation
                logger.warning(f"Reflection evaluation was '{evaluation}'. Terminating research due to unclear direction or error.")
                self.state.proposed_query = None
                self.state.current_query = None

        except Exception as e:
            logger.error(f"Error during reflection and next query generation: {e}", exc_info=True)
            self.state.proposed_query = None
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

        # Auto-approve initial query if not in interactive mode
        if not self.interactive_mode and self.state.proposed_query:
            logger.info(f"Non-interactive mode: Auto-approving initial query: {self.state.proposed_query}")
            self.state.current_query = self.state.proposed_query
            self.state.proposed_query = None # Clear proposed query

        while self.state.completed_loops < self.config.MAX_RESEARCH_LOOPS:
            if not self.state.current_query:
                logger.info("No current query. Checking for proposed query or terminating loop.")
                # In interactive mode, UI would handle this. In non-interactive, if proposed_query exists, use it.
                if not self.interactive_mode and self.state.proposed_query:
                    logger.info(f"Non-interactive mode: Auto-approving next proposed query: {self.state.proposed_query}")
                    self.state.current_query = self.state.proposed_query
                    self.state.proposed_query = None
                else: # No query to proceed with
                    logger.info("No current or auto-approved proposed query. Terminating loop.")
                    break # Exit loop if no query can be set

            logger.info(f"--- Starting Loop {self.state.completed_loops + 1} of {self.config.MAX_RESEARCH_LOOPS} for query: '{self.state.current_query}' ---")

            if not self.state.pending_source_selection:
                self._web_search()

            if self.state.pending_source_selection:
                if not self.interactive_mode:
                    if self.state.search_results:
                        logger.info(f"Non-interactive mode: Auto-selecting all {len(self.state.search_results)} sources for summarization.")
                        selected_results = self.state.search_results # Select all
                    else:
                        logger.info("Non-interactive mode: No search results to auto-select.")
                        selected_results = []
                    self._summarize_sources(selected_results=selected_results)
                    # pending_source_selection is set to False in _summarize_sources
                else:
                    # In interactive mode, we would wait for UI to provide selected_results
                    # For now, this means the loop might pause here if not handled by UI.
                    # This part of the logic is more for when a UI is driving the ResearchLoop.
                    # For a purely programmatic run (like in main.py without interactivity),
                    # this branch means we might get stuck if pending_source_selection is True
                    # and interactive_mode is True. However, main.py will set interactive_mode to False.
                    logger.info("Interactive mode: Waiting for source selection from UI (not implemented in this flow). Loop may stall here if not externally driven.")
                    # To prevent stalling in a non-UI interactive context (if that were to happen),
                    # we might need a timeout or a way for the loop to know it's not UI-driven.
                    # For this subtask, assuming main.py sets interactive_mode=False, this branch is less critical.
                    # If we are in interactive mode and pending_source_selection is true,
                    # the loop should pause, waiting for external input (e.g. from Streamlit app)
                    # to call a method that provides selected sources and then calls _summarize_sources.
                    # For the current CLI run, this state should ideally not be maintained across loop iterations
                    # without resolution.
                    # Given the current structure, if interactive_mode is True and we hit this,
                    # the loop will effectively pause as _summarize_sources won't be called.
                    # This is the desired behavior for Streamlit.
                    # For CLI, interactive_mode will be False.
                    pass # Wait for external call in interactive mode

            # Only proceed if sources have been summarized (or no sources were found/selected)
            if not self.state.pending_source_selection:
                self.state.completed_loops += 1
                if self.state.completed_loops < self.config.MAX_RESEARCH_LOOPS:
                    self._reflect_on_summary() # Generates proposed_query, clears current_query
                    # In non-interactive mode, the next iteration will auto-approve proposed_query if it exists
                    if not self.interactive_mode and self.state.proposed_query:
                        logger.info(f"Non-interactive mode: Auto-approving next query from reflection: {self.state.proposed_query}")
                        self.state.current_query = self.state.proposed_query
                        self.state.proposed_query = None
                    elif self.interactive_mode: # In interactive mode, current_query remains None after reflection
                        self.state.current_query = None # Explicitly ensure UI needs to approve next query
                        logger.info("Interactive mode: Reflection complete. Proposed query needs UI approval.")
                    else: # Non-interactive and no proposed_query from reflection (e.g. CONCLUDE)
                        logger.info("Non-interactive mode: No new query proposed by reflection or reflection led to CONCLUDE. Terminating.")
                        self.state.current_query = None # Ensure loop terminates
                else: # Max loops reached
                    logger.info(f"Max research loops ({self.config.MAX_RESEARCH_LOOPS}) reached.")
                    self.state.current_query = None # Ensure loop terminates
            else:
                # This case (pending_source_selection still true) should only happen in interactive mode
                # if the UI hasn't provided selected sources yet.
                logger.info("Loop iteration paused: Pending source selection in interactive mode.")
                # We break here to prevent an infinite loop if in interactive mode and sources are not selected.
                # The UI would typically call a method to continue.
                if self.interactive_mode: # Ensure this break only happens in interactive mode
                    break


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
