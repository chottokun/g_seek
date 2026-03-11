import asyncio
from deep_research_project.config.config import Configuration
from deep_research_project.tools.llm_client import LLMClient
from deep_research_project.core.reflection import ResearchReflector

async def test():
    config = Configuration()
    llm = LLMClient(config)
    reflector = ResearchReflector(config, llm)
    
    topic = "The history of the Internet"
    section_title = "Early development"
    section_desc = "Research the creation of ARPANET and key people involved."
    
    # Case 1: Very thin findings
    thin_findings = "The internet started with ARPANET."
    print("--- Testing Thin Findings (Expected: CONTINUE) ---")
    eval1, q1 = await reflector.reflect_and_decide(topic, section_title, section_desc, thin_findings, "English")
    print(f"Result: {eval1}, Query: {q1}")

    # Case 2: Detailed findings
    detailed_findings = "ARPANET was funded by DARPA. Vint Cerf and Bob Kahn are 'fathers of the internet'. It used packet switching."
    print("\n--- Testing Detailed Findings (Expected: CONCLUDE) ---")
    eval2, q2 = await reflector.reflect_and_decide(topic, section_title, section_desc, detailed_findings, "English")
    print(f"Result: {eval2}, Query: {q2}")

asyncio.run(test())
