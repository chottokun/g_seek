import asyncio
from deep_research_project.config.config import Configuration
from deep_research_project.tools.llm_client import LLMClient
from deep_research_project.core.reflection import ResearchReflector

async def test():
    config = Configuration()
    llm = LLMClient(config)
    reflector = ResearchReflector(config, llm)
    
    topic = "となりのトトロの背景"
    section_title = "制作のきっかけ"
    section_desc = "宮崎駿監督がなぜこの作品を作ろうと思ったのか、その背景やインスピレーションを調査してください。"
    
    # Very thin findings
    thin_findings = "となりのトトロはスタジオジブリの映画です。"
    print("--- Testing Japanese Thin Findings (Expected: CONTINUE) ---")
    eval1, q1 = await reflector.reflect_and_decide(topic, section_title, section_desc, thin_findings, "Japanese")
    print(f"Result: {eval1}, Query: {q1}")

asyncio.run(test())
