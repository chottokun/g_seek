import unittest
import asyncio
import os
import shutil
from pathlib import Path
from deep_research_project.core.skills_manager import SkillRegistry

class TestSkillRegistryAsync(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.test_dir = Path("test_skills_async")
        if self.test_dir.exists():
            shutil.rmtree(self.test_dir)
        self.registry = SkillRegistry(skills_dir=str(self.test_dir))

    async def asyncTearDown(self):
        if self.test_dir.exists():
            shutil.rmtree(self.test_dir)

    async def test_save_skill_async(self):
        skill_id = "test-skill"
        name = "Test Skill"
        description = "Test Description"
        content = "Test Content"

        # Test that we can await it
        await self.registry.save_skill(skill_id, name, description, content)

        # Verify it was saved
        skill_file = self.test_dir / skill_id / "SKILL.md"
        self.assertTrue(skill_file.exists())

        with open(skill_file, "r", encoding="utf-8") as f:
            saved_content = f.read()

        self.assertIn(name, saved_content)
        self.assertIn(description, saved_content)
        self.assertIn(content, saved_content)

        # Verify it's in the registry
        skill_data = self.registry.get_skill(skill_id)
        self.assertIsNotNone(skill_data)
        self.assertEqual(skill_data["name"], name)
        self.assertEqual(skill_data["content"], content)

    async def test_concurrent_save_skills(self):
        # Save multiple skills concurrently
        tasks = []
        for i in range(10):
            tasks.append(self.registry.save_skill(
                f"skill-{i}", f"Skill {i}", f"Desc {i}", f"Content {i}"
            ))

        await asyncio.gather(*tasks)

        for i in range(10):
            skill_id = f"skill-{i}"
            skill_file = self.test_dir / skill_id / "SKILL.md"
            self.assertTrue(skill_file.exists(), f"{skill_id} file should exist")
            self.assertIn(skill_id, self.registry.skills)

if __name__ == "__main__":
    unittest.main()
