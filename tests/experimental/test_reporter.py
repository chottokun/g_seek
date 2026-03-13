import asyncio
from deep_research_project.config.config import Configuration
from deep_research_project.tools.llm_client import LLMClient
from deep_research_project.core.reporting import ResearchReporter

async def test():
    config = Configuration()
    llm = LLMClient(config)
    reporter = ResearchReporter(llm)
    
    findings = ["The sky is blue.", "Grass is green."]
    sources = [{"title": "Science", "link": "http://science.com"}]
    
    print("Testing English Report...")
    report_en = await reporter.finalize_report("Nature", findings, sources, "English")
    if "```json" in report_en:
        print("SUCCESS: JSON block found in English report.")
    else:
        print("FAILURE: JSON block NOT found in English report.")
        print("Report start:", report_en[:200])
        print("Report end:", report_en[-500:])

    print("\nTesting Japanese Report...")
    report_ja = await reporter.finalize_report("自然", findings, sources, "Japanese")
    if "```json" in report_ja:
        print("SUCCESS: JSON block found in Japanese report.")
    else:
        print("FAILURE: JSON block NOT found in Japanese report.")

asyncio.run(test())
