import os
import logging
import asyncio
from typing import List, Dict, Optional
from pathlib import Path
import yaml
import re

logger = logging.getLogger(__name__)

class SkillRegistry:
    """Manages discovery, loading, and registration of modular skills (Anthropic style)."""
    
    def __init__(self, static_skills_dir: str = ".agents/skills", dynamic_skills_dir: str = "data/skills"):
        self.static_skills_dir = Path(static_skills_dir)
        self.dynamic_skills_dir = Path(dynamic_skills_dir)
        self.static_skills_dir.mkdir(parents=True, exist_ok=True)
        self.dynamic_skills_dir.mkdir(parents=True, exist_ok=True)
        self.skills: Dict[str, Dict] = {}
        self._discover_skills()

    def _discover_skills(self):
        """Scans the static and dynamic directories for folders containing SKILL.md."""
        self._scan_directory(self.static_skills_dir, is_dynamic=False)
        self._scan_directory(self.dynamic_skills_dir, is_dynamic=True)

    def _scan_directory(self, target_dir: Path, is_dynamic: bool):
        if not target_dir.exists():
            return

        for skill_path in target_dir.iterdir():
            if skill_path.is_dir():
                skill_file = skill_path / "SKILL.md"
                if skill_file.exists():
                    try:
                        skill_data = self._parse_skill_file(skill_file)
                        skill_data["id"] = skill_path.name
                        skill_data["path"] = str(skill_path)
                        skill_data["is_dynamic"] = is_dynamic
                        self.skills[skill_path.name] = skill_data
                        logger.info(f"Discovered {'dynamic' if is_dynamic else 'static'} skill: {skill_data.get('name', skill_path.name)} ({skill_path.name})")
                    except Exception as e:
                        logger.error(f"Failed to parse skill at {skill_file}: {e}")

    def _parse_skill_file(self, file_path: Path) -> Dict:
        """Parses the YAML frontmatter and body of a SKILL.md file."""
        with open(file_path, "r", encoding="utf-8") as f:
            content = f.read()

        # Simple YAML frontmatter regex
        match = re.match(r"^---\s*\n(.*?)\n---\s*\n(.*)$", content, re.DOTALL)
        if match:
            yaml_content = match.group(1)
            markdown_body = match.group(2)
            data = yaml.safe_load(yaml_content)
            data["content"] = markdown_body
            return data
        else:
            # Fallback if no frontmatter
            return {
                "name": file_path.parent.name,
                "description": "No description provided.",
                "content": content
            }

    def list_skills(self) -> List[Dict]:
        """Returns metadata for all discovered skills (Progressive Disclosure)."""
        return [
            {
                "id": skill_id,
                "name": data["name"],
                "description": data["description"]
            }
            for skill_id, data in self.skills.items()
        ]

    def get_skill(self, skill_id: str) -> Optional[Dict]:
        """Retrieves the full content of a specific skill."""
        return self.skills.get(skill_id)

    async def save_skill(self, skill_id: str, name: str, description: str, content: str, created_at: Optional[str] = None):
        """Saves or updates a skill in the dynamic folder structure asynchronously."""
        skill_path = self.dynamic_skills_dir / skill_id
        
        frontmatter = {
            "name": name,
            "description": description
        }
        if created_at:
            frontmatter["created_at"] = created_at
            
        def _sync_save():
            skill_path.mkdir(parents=True, exist_ok=True)
            skill_file = skill_path / "SKILL.md"
            yaml_str = yaml.dump(frontmatter, allow_unicode=True, default_flow_style=False).strip()
            full_content = f"---\n{yaml_str}\n---\n\n{content}"

            with open(skill_file, "w", encoding="utf-8") as f:
                f.write(full_content)

        await asyncio.to_thread(_sync_save)
        
        # Partially reload registry (optimized)
        self.skills[skill_id] = {
            "id": skill_id,
            "name": name,
            "description": description,
            "content": content,
            "path": str(skill_path),
            "is_dynamic": True
        }

# For backward compatibility during migration
SkillsManager = SkillRegistry
