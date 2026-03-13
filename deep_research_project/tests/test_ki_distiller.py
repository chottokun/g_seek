import unittest
import os
import json
import shutil
import tempfile
from unittest.mock import MagicMock, AsyncMock
from deep_research_project.core.ki_distiller import KIDistiller
from deep_research_project.tools.llm_client import LLMClient
from deep_research_project.core.prompts import KI_METADATA_PROMPT_EN, KI_METADATA_PROMPT_JA

class TestKIDistiller(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.test_dir = tempfile.mkdtemp()
        self.mock_llm = MagicMock(spec=LLMClient)
        self.distiller = KIDistiller(self.mock_llm, self.test_dir)

    async def asyncTearDown(self):
        shutil.rmtree(self.test_dir)

    async def test_distill_research_happy_path_en(self):
        report = "This is a great research report about AI."
        language = "English"
        mock_metadata = {
            "title": "AI Research",
            "summary": "AI is evolving rapidly.",
            "keywords": ["AI", "Technology"],
            "related_topics": ["Machine Learning"]
        }
        self.mock_llm.generate_text = AsyncMock(return_value=json.dumps(mock_metadata))

        ki_path = await self.distiller.distill_research(report, language)

        # Verify directory creation
        self.assertTrue(os.path.exists(ki_path))
        self.assertTrue(os.path.exists(os.path.join(ki_path, "metadata.json")))
        self.assertTrue(os.path.exists(os.path.join(ki_path, "artifacts", "research_report.md")))

        # Verify metadata.json content
        with open(os.path.join(ki_path, "metadata.json"), "r", encoding="utf-8") as f:
            saved_metadata = json.load(f)
            self.assertEqual(saved_metadata["title"], "AI Research")
            self.assertEqual(saved_metadata["summary"], "AI is evolving rapidly.")
            self.assertEqual(saved_metadata["keywords"], ["AI", "Technology"])
            self.assertEqual(saved_metadata["related_topics"], ["Machine Learning"])
            self.assertIn("created_at", saved_metadata)

        # Verify report content
        with open(os.path.join(ki_path, "artifacts", "research_report.md"), "r", encoding="utf-8") as f:
            saved_report = f.read()
            self.assertEqual(saved_report, report)

        # Verify prompt used
        call_args = self.mock_llm.generate_text.call_args
        self.assertIn(KI_METADATA_PROMPT_EN, call_args.kwargs['prompt'])
        self.assertIn(report, call_args.kwargs['prompt'])

    async def test_distill_research_happy_path_ja(self):
        report = "AIに関する素晴らしいリサーチレポートです。"
        language = "Japanese"
        mock_metadata = {
            "title": "AIリサーチ",
            "summary": "AIは急速に進化しています。",
            "keywords": ["AI", "テクノロジー"],
            "related_topics": ["機械学習"]
        }
        self.mock_llm.generate_text = AsyncMock(return_value=json.dumps(mock_metadata))

        ki_path = await self.distiller.distill_research(report, language)

        # Verify prompt used
        call_args = self.mock_llm.generate_text.call_args
        self.assertIn(KI_METADATA_PROMPT_JA, call_args.kwargs['prompt'])
        self.assertIn(report, call_args.kwargs['prompt'])

    async def test_json_cleanup_markdown(self):
        report = "Report content"
        mock_response = "Here is the JSON:\n```json\n{\"title\": \"Markdown JSON\", \"summary\": \"Tested\"}\n```\nHope it helps!"
        self.mock_llm.generate_text = AsyncMock(return_value=mock_response)

        ki_path = await self.distiller.distill_research(report, "English")

        with open(os.path.join(ki_path, "metadata.json"), "r", encoding="utf-8") as f:
            saved_metadata = json.load(f)
            self.assertEqual(saved_metadata["title"], "Markdown JSON")

    async def test_json_cleanup_braces(self):
        report = "Report content"
        mock_response = "Surrounding text {\"title\": \"Braces JSON\", \"summary\": \"Tested\"} more text"
        self.mock_llm.generate_text = AsyncMock(return_value=mock_response)

        ki_path = await self.distiller.distill_research(report, "English")

        with open(os.path.join(ki_path, "metadata.json"), "r", encoding="utf-8") as f:
            saved_metadata = json.load(f)
            self.assertEqual(saved_metadata["title"], "Braces JSON")

    async def test_fallback_mechanism(self):
        report = "Report content"
        self.mock_llm.generate_text = AsyncMock(return_value="Invalid JSON content")

        ki_path = await self.distiller.distill_research(report, "English")

        self.assertTrue(os.path.exists(ki_path))
        with open(os.path.join(ki_path, "metadata.json"), "r", encoding="utf-8") as f:
            saved_metadata = json.load(f)
            self.assertEqual(saved_metadata["title"], "Untitled Research")
            self.assertEqual(saved_metadata["summary"], "Full summary unavailable due to parsing error.")

if __name__ == "__main__":
    unittest.main()
