import pytest
import os
import tempfile
from pathlib import Path
from deep_research_project.core.skills_manager import SkillRegistry

def test_skill_registry_directories():
    """Test that SkillRegistry correctly separates static and dynamic skills."""
    with tempfile.TemporaryDirectory() as static_dir, tempfile.TemporaryDirectory() as dynamic_dir:
        # Create a mock static skill
        static_skill_path = Path(static_dir) / "static-skill-1"
        static_skill_path.mkdir()
        with open(static_skill_path / "SKILL.md", "w", encoding="utf-8") as f:
            f.write("---\nname: Static Skill\ndescription: A static skill\n---\nStatic content")

        # Create a mock dynamic skill
        dynamic_skill_path = Path(dynamic_dir) / "dynamic-skill-1"
        dynamic_skill_path.mkdir()
        with open(dynamic_skill_path / "SKILL.md", "w", encoding="utf-8") as f:
            f.write("---\nname: Dynamic Skill\ndescription: A dynamic skill\n---\nDynamic content")

        # Initialize registry
        registry = SkillRegistry(static_skills_dir=static_dir, dynamic_skills_dir=dynamic_dir)
        
        # Verify discovery
        assert len(registry.skills) == 2
        assert "static-skill-1" in registry.skills
        assert "dynamic-skill-1" in registry.skills
        
        # Verify static/dynamic flag
        assert registry.skills["static-skill-1"]["is_dynamic"] is False
        assert registry.skills["dynamic-skill-1"]["is_dynamic"] is True

        # Test save_skill (should save to dynamic dir)
        registry.save_skill("new-dynamic-skill", "New Skill", "Desc", "Content")
        
        new_skill_path = Path(dynamic_dir) / "new-dynamic-skill" / "SKILL.md"
        assert new_skill_path.exists(), "New skill must be saved in the dynamic directory"
        
        # Static directory should not contain the new skill
        new_skill_static_path = Path(static_dir) / "new-dynamic-skill" / "SKILL.md"
        assert not new_skill_static_path.exists(), "New skill must NOT be saved in the static directory"
        
        # Registry memory should be updated
        assert "new-dynamic-skill" in registry.skills
        assert registry.skills["new-dynamic-skill"]["is_dynamic"] is True
