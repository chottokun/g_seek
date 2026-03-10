import unittest
import tempfile
import shutil
from pathlib import Path
import os
from deep_research_project.core.skills_manager import SkillRegistry

class TestSkillRegistry(unittest.TestCase):
    def setUp(self):
        # Create a temporary directory for skills
        self.test_dir = tempfile.mkdtemp()
        self.skills_dir = Path(self.test_dir) / "skills"

    def tearDown(self):
        # Remove the directory after the test
        shutil.rmtree(self.test_dir)

    def test_discover_skills_empty(self):
        # Test with no skills directory
        registry = SkillRegistry(skills_dir=str(self.skills_dir))
        self.assertEqual(len(registry.skills), 0)

    def test_discover_skills_success(self):
        # Setup a valid skill
        skill_id = "test_skill"
        skill_path = self.skills_dir / skill_id
        skill_path.mkdir(parents=True)
        skill_file = skill_path / "SKILL.md"

        content = """---
name: Test Skill
description: A test skill description
---
Skill body content
"""
        with open(skill_file, "w", encoding="utf-8") as f:
            f.write(content)

        registry = SkillRegistry(skills_dir=str(self.skills_dir))

        self.assertIn(skill_id, registry.skills)
        skill_data = registry.skills[skill_id]
        self.assertEqual(skill_data["name"], "Test Skill")
        self.assertEqual(skill_data["description"], "A test skill description")
        self.assertEqual(skill_data["content"].strip(), "Skill body content")
        self.assertEqual(skill_data["id"], skill_id)

    def test_discover_skills_fallback(self):
        # Setup a skill without frontmatter
        skill_id = "fallback_skill"
        skill_path = self.skills_dir / skill_id
        skill_path.mkdir(parents=True)
        skill_file = skill_path / "SKILL.md"

        content = "Just plain content without frontmatter"
        with open(skill_file, "w", encoding="utf-8") as f:
            f.write(content)

        registry = SkillRegistry(skills_dir=str(self.skills_dir))

        self.assertIn(skill_id, registry.skills)
        skill_data = registry.skills[skill_id]
        self.assertEqual(skill_data["name"], skill_id)
        self.assertEqual(skill_data["description"], "No description provided.")
        self.assertEqual(skill_data["content"], content)

    def test_discover_skills_ignore_non_skill_dirs(self):
        # Setup a directory without SKILL.md
        other_dir = self.skills_dir / "not_a_skill"
        other_dir.mkdir(parents=True)

        # Setup a file in skills dir
        some_file = self.skills_dir / "random.txt"
        some_file.write_text("hello")

        registry = SkillRegistry(skills_dir=str(self.skills_dir))
        self.assertEqual(len(registry.skills), 0)

    def test_list_skills(self):
        # Setup two skills
        for i in range(2):
            skill_id = f"skill_{i}"
            skill_path = self.skills_dir / skill_id
            skill_path.mkdir(parents=True)
            (skill_path / "SKILL.md").write_text(f"---\nname: Name {i}\ndescription: Desc {i}\n---\nContent {i}")

        registry = SkillRegistry(skills_dir=str(self.skills_dir))
        skills_list = registry.list_skills()

        self.assertEqual(len(skills_list), 2)
        # Sort to ensure deterministic check
        skills_list.sort(key=lambda x: x["id"])

        self.assertEqual(skills_list[0]["id"], "skill_0")
        self.assertEqual(skills_list[0]["name"], "Name 0")
        self.assertEqual(skills_list[1]["id"], "skill_1")
        self.assertEqual(skills_list[1]["description"], "Desc 1")

    def test_get_skill(self):
        skill_id = "target_skill"
        skill_path = self.skills_dir / skill_id
        skill_path.mkdir(parents=True)
        (skill_path / "SKILL.md").write_text("---\nname: Target\ndescription: Target Desc\n---\nFull Content")

        registry = SkillRegistry(skills_dir=str(self.skills_dir))

        # Success case
        skill = registry.get_skill(skill_id)
        self.assertIsNotNone(skill)
        self.assertEqual(skill["name"], "Target")
        self.assertEqual(skill["content"].strip(), "Full Content")

        # Failure case
        self.assertIsNone(registry.get_skill("non_existent"))

    def test_save_skill(self):
        registry = SkillRegistry(skills_dir=str(self.skills_dir))

        skill_id = "new_skill"
        name = "New Skill"
        desc = "New Description"
        content = "New Content"

        registry.save_skill(skill_id, name, desc, content)

        # Verify in memory
        self.assertIn(skill_id, registry.skills)
        self.assertEqual(registry.skills[skill_id]["name"], name)

        # Verify on disk
        skill_file = self.skills_dir / skill_id / "SKILL.md"
        self.assertTrue(skill_file.exists())
        file_content = skill_file.read_text(encoding="utf-8")
        self.assertIn("name: New Skill", file_content)
        self.assertIn("New Content", file_content)

if __name__ == '__main__':
    unittest.main()
