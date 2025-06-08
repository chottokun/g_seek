from deep_research_project.config.config import Configuration
from .state import ResearchState, SearchResult, Source # Adjusted import path

# Placeholder for LLM and Search Tool clients (to be implemented in Step 5)
from deep_research_project.tools.llm_client import LLMClient # Example
from deep_research_project.tools.search_client import SearchClient # Example
from deep_research_project.tools.content_retriever import ContentRetriever # Added import
import logging
import json # Added for knowledge graph extraction
from typing import List, Optional, Callable

logger = logging.getLogger(__name__)


def split_text_into_chunks(text: str, chunk_size: int, chunk_overlap: int) -> List[str]:
    """
    Splits a given text into overlapping chunks.

    Args:
        text: The text content to be split.
        chunk_size: The maximum size of each chunk in characters.
        chunk_overlap: The number of characters to overlap between consecutive chunks.

    Returns:
        A list of text chunks.

    Raises:
        ValueError: If chunk_size is non-positive, or if chunk_overlap is negative or
                    greater than or equal to chunk_size.
    """
    if not text:
        return []

    if chunk_size <= 0:
        raise ValueError("Chunk size must be positive.")
    if chunk_overlap < 0:
        raise ValueError("Chunk overlap cannot be negative.")
    if chunk_overlap >= chunk_size:
        raise ValueError("Chunk overlap must be less than chunk size.")

    text_len = len(text)
    if text_len <= chunk_size:
        return [text]

    chunks = []
    idx = 0
    while idx < text_len:
        end_idx = idx + chunk_size
        chunks.append(text[idx:end_idx])

        # If the current chunk reaches or exceeds the end of the text, stop
        if end_idx >= text_len:
            break

        idx += (chunk_size - chunk_overlap)

        # Safety break in case of misconfiguration leading to non-positive step,
        # though validation should prevent this.
        if (chunk_size - chunk_overlap) <= 0:
            logger.error("Chunk step is non-positive, breaking to prevent infinite loop.")
            break

    return chunks


class ResearchLoop:
    def __init__(self, config: Configuration, state: ResearchState, progress_callback: Optional[Callable[[str], None]] = None):
        self.config = config
        self.state = state
        self.interactive_mode = config.INTERACTIVE_MODE  # Store interactive_mode
        self.progress_callback = progress_callback
        logger.info(f"Initializing LLM and Search clients for ResearchLoop. Interactive mode: {self.interactive_mode}")
        try:
            self.llm_client = LLMClient(config)
            self.search_client = SearchClient(config)
            self.content_retriever = ContentRetriever(config=self.config) # Pass config
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
        if self.progress_callback:
            self.progress_callback(f"Processing {len(selected_results)} sources for summarization...")
        final_summary = "" # Initialize final_summary to ensure it has a value

        try:
            chunk_size = self.config.SUMMARIZATION_CHUNK_SIZE_CHARS
            chunk_overlap = self.config.SUMMARIZATION_CHUNK_OVERLAP_CHARS

            if not selected_results:
                logger.info("No selected results to summarize.")
                self.state.new_information = "No sources were selected for summarization."
                # self.state.pending_source_selection is set in finally
                return

            logger.info(f"Attempting to fetch and summarize content for {len(selected_results)} selected search results using chunking.")

            if self.state.fetched_content is None:
                self.state.fetched_content = {}

            all_chunk_summaries = []

            for result in selected_results:
                link = result['link']
                if self.progress_callback:
                    self.progress_callback(f"Processing source: {result['link']}")
                logger.info(f"Processing source: {link}")
                content_to_use_for_chunking = None

                if self.config.USE_SNIPPETS_ONLY_MODE:
                    if self.progress_callback:
                        self.progress_callback(f"Using snippet directly for {result['link']} (Snippet-Only Mode).")
                    logger.info(f"Snippet-only mode is ON. Using snippet directly for {link}.")
                    content_to_use_for_chunking = result.get('snippet', '')
                    # Store the snippet in fetched_content for consistency,
                    # especially if KG or other future steps might want to know what was processed.
                    if link not in self.state.fetched_content or not self.state.fetched_content[link]:
                        self.state.fetched_content[link] = content_to_use_for_chunking
                else: # Attempt to fetch full text
                    if link not in self.state.fetched_content or not self.state.fetched_content[link]:
                        logger.info(f"Fetching full text for: {link}")
                        full_text = self.content_retriever.retrieve_and_extract(link)
                        if full_text:
                            self.state.fetched_content[link] = full_text
                            logger.debug(f"Successfully fetched text for {link} (length: {len(full_text)}).")
                        else:
                            logger.warning(f"Failed to fetch full text for {link}. Using snippet as fallback.")
                            self.state.fetched_content[link] = result.get('snippet', '')
                    content_to_use_for_chunking = self.state.fetched_content.get(link)

                # Apply truncation before checking if content is empty/whitespace
                limit = self.config.MAX_TEXT_LENGTH_PER_SOURCE_CHARS
                if content_to_use_for_chunking: # Ensure there's content before trying to get its length
                    original_length = len(content_to_use_for_chunking)
                    if limit > 0 and original_length > limit:
                        logger.info(f"Content for source {result['link']} (original length: {original_length}) exceeds limit ({limit}). Truncating.")
                        content_to_use_for_chunking = content_to_use_for_chunking[:limit]
                        logger.debug(f"Truncated content length for {result['link']}: {len(content_to_use_for_chunking)}")

                if not content_to_use_for_chunking or content_to_use_for_chunking.isspace():
                    logger.warning(f"No content available for source: {link} (after considering snippet/full text mode and truncation). Skipping.")
                    continue

                try:
                    chunks = split_text_into_chunks(content_to_use_for_chunking, chunk_size, chunk_overlap)
                    logger.info(f"Split content from {link} (using {'snippet' if self.config.USE_SNIPPETS_ONLY_MODE else 'full text'}, length {len(content_to_use_for_chunking)}) into {len(chunks)} chunks.")
                    if self.progress_callback and chunks:
                        self.progress_callback(f"Summarizing {len(chunks)} chunks for source {result['link']}...")
                except ValueError as e:
                    logger.error(f"Error splitting text for source {link}: {e}. Skipping this source.")
                    continue

                for i, chunk_text in enumerate(chunks):
                    chunk_summary_prompt = (
                        f"This is a segment of a larger document. "
                        f"Summarize the following text segment focusing on information relevant to the research query: '{self.state.current_query}'.\n\n"
                        f"Text Segment:\n---\n{chunk_text}\n---\n\n"
                        f"Concise Summary of the Segment:"
                    )
                    try:
                        logger.debug(f"Summarizing chunk {i+1}/{len(chunks)} for source {link}...")
                        chunk_summary = self.llm_client.generate_text(prompt=chunk_summary_prompt)
                        if chunk_summary and not chunk_summary.isspace():
                            all_chunk_summaries.append(chunk_summary)
                            logger.debug(f"Chunk {i+1}/{len(chunks)} summary (len: {len(chunk_summary)}): {chunk_summary[:100]}...")
                        else:
                            logger.warning(f"Empty summary received for chunk {i+1}/{len(chunks)} of source {link}.")
                    except Exception as e:
                        logger.error(f"Error summarizing chunk {i+1}/{len(chunks)} for source {link}: {e}", exc_info=True)
                        # Continue to next chunk

            if not all_chunk_summaries:
                logger.warning("No content could be summarized from any chunks of the selected sources.")
                self.state.new_information = "No content could be summarized from the selected sources."
                # self.state.pending_source_selection is set in finally
                # Call _extract_entities_and_relations here as per instruction,
                # though it won't do much if new_information indicates no summary.
                self._extract_entities_and_relations()
                return

            logger.info(f"Generated {len(all_chunk_summaries)} chunk summaries in total.")
            if self.progress_callback and all_chunk_summaries:
                self.progress_callback(f"Consolidating {len(all_chunk_summaries)} chunk summaries...")
            combined_chunk_summaries = "\n\n---\n\n".join(all_chunk_summaries)

            # Optional: Check length of combined_chunk_summaries if it could be an issue for the consolidation prompt
            # For example: if len(combined_chunk_summaries) > some_large_threshold: logger.warning(...)

            consolidation_prompt = (
                f"The following are individual summaries from different segments of text(s) related to the research query: '{self.state.current_query}'.\n"
                f"Combine these into a single, coherent, and comprehensive summary that addresses the research query.\n\n"
                f"Individual Summaries:\n---\n{combined_chunk_summaries}\n---\n\n"
                f"Final Comprehensive Summary:"
            )

            logger.info("Consolidating chunk summaries into a final summary...")
            try:
                final_summary = self.llm_client.generate_text(prompt=consolidation_prompt)
                self.state.new_information = final_summary
                if self.progress_callback and self.state.new_information and "Error" not in self.state.new_information: # Check error in string is a bit weak
                    self.progress_callback("Final summary for current query generated.")
                logger.info(f"Final summary generated (length: {len(final_summary)}).")
            except Exception as e:
                logger.error(f"Error consolidating chunk summaries for query '{self.state.current_query}': {e}", exc_info=True)
                self.state.new_information = "Error occurred during final summary consolidation."
                # If consolidation fails, we might still want to keep the chunk summaries
                # or some part of it, but for now, just an error message.

            # Update accumulated summary and sources gathered
            if self.state.new_information and "Error occurred" not in self.state.new_information:
                 self.state.accumulated_summary += f"\n\n## Findings for query: {self.state.current_query}\n{self.state.new_information}"

            for res in selected_results: # Always record sources that were part of the selection attempt
                if res['link'] not in [s['link'] for s in self.state.sources_gathered]:
                    self.state.sources_gathered.append(Source(title=res['title'], link=res['link']))

            logger.debug(f"Accumulated summary length: {len(self.state.accumulated_summary)}")

        except Exception as e: # Catch-all for unexpected errors in the summarization process
            logger.error(f"An unexpected error occurred in _summarize_sources: {e}", exc_info=True)
            self.state.new_information = "An unexpected error occurred during source summarization."
        finally:
            self.state.pending_source_selection = False # Summarization attempt made (or skipped), selection process is over

        # After generating new_information (or error message), extract entities and relations
        # This call was already here and should be fine as _extract_entities_and_relations checks new_information validity.
        self._extract_entities_and_relations()

    def format_follow_up_prompt(self, context_text: str, follow_up_question: str) -> str:
        logger.debug(f"Formatting prompt for follow-up: {follow_up_question[:50]}...")
        if not context_text: # Should not happen if called correctly from streamlit_app
            logger.warning("No context text provided for formatting follow-up prompt. Using a generic prompt.")
            # Fallback prompt if context is missing, though streamlit_app.py should check context first.
            return f"Please answer the following question: {follow_up_question}\n\nAnswer:"

        prompt = (
            f"Based on the provided research report context below, please answer the user's follow-up question.\n\n"
            f"Research Report Context:\n"
            f"---\n"
            f"{context_text}\n"
            f"---\n\n"
            f"User's Follow-up Question: {follow_up_question}\n\n"
            f"Answer:"
        )
        return prompt

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
            f"Your task is to identify key entities (e.g., people, organizations, concepts, locations, technologies, events) and their relationships from the provided text. "
            f"Format your output STRICTLY as a single, valid JSON object with two main keys: \"nodes\" and \"edges\".\n\n"

            f"The \"nodes\" key should contain a list of objects. Each node object must have:\n"
            f"  - \"id\": A unique string identifier for the node (e.g., \"entity_name_or_concept_1\"). This ID must be unique within the list of nodes.\n"
            f"  - \"label\": The name or label of the entity or concept (e.g., \"Dr. Alice Smith\", \"Climate Change\", \"AlphaCorp Inc.\").\n"
            f"  - \"type\": A category for the entity (e.g., \"Person\", \"Organization\", \"Concept\", \"Location\", \"Technology\", \"Event\", \"Problem\", \"Solution\"). Use your best judgment for typing if not an obvious category.\n\n"

            f"The \"edges\" key should contain a list of objects. Each edge object must have:\n"
            f"  - \"source\": The \"id\" of the source node for the relationship.\n"
            f"  - \"target\": The \"id\" of the target node for the relationship.\n"
            f"  - \"label\": A concise description of the relationship (e.g., \"develops\", \"impacts\", \"is located in\", \"is a type of\").\n\n"

            f"Important Rules:\n"
            f"- All node \"id\" values referenced in \"edges\" (as \"source\" or \"target\") MUST be defined in the \"nodes\" list.\n"
            f"- If no relevant entities or relationships are found in the text, you MUST return a JSON object with empty lists for \"nodes\" and \"edges\", like this: {{\"nodes\": [], \"edges\": []}}.\n"
            f"- Ensure the entire output is a single, valid JSON object. Do not include any explanatory text before or after the JSON.\n\n"

            f"Example:\n"
            f"Text:\n"
            f"---\n"
            f"Dr. Eva Rostova from Innovatech Solutions published a paper on AI advancements. Innovatech Solutions is based in Neo-Tokyo.\n"
            f"---\n"
            f"JSON Output:\n"
            f"{{\n"
            f"  \"nodes\": [\n"
            f"    {{\"id\": \"eva_rostova_person_1\", \"label\": \"Dr. Eva Rostova\", \"type\": \"Person\"}},\n"
            f"    {{\"id\": \"innovatech_solutions_org_1\", \"label\": \"Innovatech Solutions\", \"type\": \"Organization\"}},\n"
            f"    {{\"id\": \"ai_advancements_concept_1\", \"label\": \"AI advancements\", \"type\": \"Concept\"}},\n"
            f"    {{\"id\": \"neo_tokyo_location_1\", \"label\": \"Neo-Tokyo\", \"type\": \"Location\"}}\n"
            f"  ],\n"
            f"  \"edges\": [\n"
            f"    {{\"source\": \"eva_rostova_person_1\", \"target\": \"innovatech_solutions_org_1\", \"label\": \"works at\"}},\n"
            f"    {{\"source\": \"eva_rostova_person_1\", \"target\": \"ai_advancements_concept_1\", \"label\": \"published paper on\"}},\n"
            f"    {{\"source\": \"innovatech_solutions_org_1\", \"target\": \"neo_tokyo_location_1\", \"label\": \"is based in\"}}\n"
            f"  ]\n"
            f"}}\n\n"

            f"Now, process the following text:\n"
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
                except json.JSONDecodeError as e: # Ensure this line is indented correctly relative to its try
                    # These lines must be indented further than the except
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
                f"Original Research Topic: {self.state.research_topic}\n\n"
                f"Current Accumulated Summary (based on previous search queries):\n{self.state.accumulated_summary}\n\n"
                f"Your task is to analyze the \"Current Accumulated Summary\" in the context of the \"Original Research Topic\".\n"
                f"Instructions:\n"
                f"1. Evaluate if the \"Current Accumulated Summary\" has sufficiently explored the \"Original Research Topic\". "
                f"Possible evaluations are: CONTINUE, MODIFY_QUERY, CONCLUDE.\n"
                f"   - Use CONCLUDE if the \"Original Research Topic\" seems well-covered by the summary or if further investigation "
                f"seems unlikely to yield more relevant information *for the Original Research Topic*.\n"
                f"   - Use CONTINUE if the summary is relevant but needs more depth *on the Original Research Topic*.\n"
                f"   - Use MODIFY_QUERY if the summary suggests a closely related sub-topic that is critical for understanding "
                f"the \"Original Research Topic\" but requires a slightly different query angle. The new query must still "
                f"directly serve the \"Original Research Topic\".\n\n"
                f"2. Based on your evaluation, and strictly focusing on advancing the understanding of the \"Original Research Topic\":\n"
                f"   - If CONTINUE or MODIFY_QUERY: Identify key knowledge gaps in the \"Current Accumulated Summary\" "
                f"*specifically concerning the Original Research Topic*.\n"
                f"   - Suggest a new, specific search query (max 12 words) that directly targets these gaps to better "
                f"understand the \"Original Research Topic\".\n"
                f"   - If CONCLUDE: The new search query should be 'None'.\n\n"
                f"3. Ensure the new search query is not a repeat of previous queries (if known) and is a logical next step "
                f"to deepen insights *about the Original Research Topic*. Do not suggest queries that deviate to unrelated topics.\n\n"
                f"Format your response exactly as follows:\n"
                f"EVALUATION: <CONTINUE|MODIFY_QUERY|CONCLUDE>\n"
                f"QUERY: <Your new search query, strictly related to the Original Research Topic, or None>\n\n"
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
            elif evaluation == "MODIFY_QUERY": # Changed from MODIFY_TOPIC
                logger.info("Reflection evaluation is MODIFY_QUERY. A new query will be proposed.")
                if next_query:
                    self.state.proposed_query = next_query # Propose the query directly
                    self.state.current_query = None # Ensure current_query is cleared until approval
                    logger.info(f"New query proposed based on query modification: {self.state.proposed_query}")
                else:
                    logger.warning("MODIFY_QUERY suggested, but no new query provided by LLM. Concluding research.")
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
        if self.progress_callback:
            self.progress_callback(f"Starting research loop for topic: '{self.state.research_topic}'")
        logger.info(f"Starting research loop for topic: '{self.state.research_topic}'")

        if self.progress_callback:
            self.progress_callback("Generating initial query...")
        self._generate_initial_query()
        if self.progress_callback and self.state.proposed_query:
            self.progress_callback(f"Initial query proposed: {self.state.proposed_query[:50]}...")


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

            if self.progress_callback:
                self.progress_callback(f"--- Starting Loop {self.state.completed_loops + 1} of {self.config.MAX_RESEARCH_LOOPS} for query: '{self.state.current_query[:50]}...' ---")
            logger.info(f"--- Starting Loop {self.state.completed_loops + 1} of {self.config.MAX_RESEARCH_LOOPS} for query: '{self.state.current_query}' ---")

            if not self.state.pending_source_selection:
                if self.progress_callback:
                    self.progress_callback(f"Performing web search for: '{self.state.current_query[:50]}...'")
                self._web_search()
                if self.progress_callback:
                    self.progress_callback(f"Web search complete. Found {len(self.state.search_results) if self.state.search_results else 0} results.")


            if self.state.pending_source_selection:
                if not self.interactive_mode:
                    if self.state.search_results:
                        logger.info(f"Non-interactive mode: Auto-selecting all {len(self.state.search_results)} sources for summarization.")
                        selected_results = self.state.search_results # Select all
                        if self.progress_callback:
                             self.progress_callback(f"Auto-selecting {len(selected_results)} sources for summarization...")
                    else:
                        logger.info("Non-interactive mode: No search results to auto-select.")
                        selected_results = []
                        if self.progress_callback:
                            self.progress_callback("No search results to auto-select for summarization.")
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
                    if self.progress_callback:
                        self.progress_callback("Reflecting on summary and planning next steps...")
                    self._reflect_on_summary() # Generates proposed_query, clears current_query
                    if self.progress_callback and self.state.proposed_query:
                        self.progress_callback(f"Next query proposed after reflection: {self.state.proposed_query[:50]}...")
                    elif self.progress_callback and not self.state.current_query: # CONCLUDE case from reflection
                        self.progress_callback("Reflection led to CONCLUDE. Finalizing research.")

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


        if self.progress_callback:
            self.progress_callback("Finalizing research summary...")
        self._finalize_summary()
        logger.info("Research loop finished.")
        if self.progress_callback:
            self.progress_callback("Research loop finished.")
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
