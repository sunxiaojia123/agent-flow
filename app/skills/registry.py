"""Skill registry — manages public/ and custom/ skill loading."""

from pathlib import Path
from app.skills.loader import parse_skill
from app.skills.models import Skill

SKILLS_DIR = Path("skills")


class SkillRegistry:
    def __init__(self, base_dir: Path | None = None):
        self._base = base_dir or SKILLS_DIR
        self._skills: dict[str, Skill] = {}
        self._by_category: dict[str, list[str]] = {}

    def load_all(self):
        """Load skills from public/ and custom/ directories."""
        self._skills.clear()
        self._by_category.clear()

        for subdir in ("public", "custom"):
            dir_path = self._base / subdir
            if not dir_path.exists():
                continue
            for skill_dir in sorted(dir_path.iterdir()):
                if not skill_dir.is_dir():
                    continue
                skill_file = skill_dir / "SKILL.md"
                if not skill_file.exists():
                    continue
                try:
                    skill = parse_skill(skill_file)
                    self._skills[skill.name] = skill
                    cat = skill.category
                    if cat not in self._by_category:
                        self._by_category[cat] = []
                    self._by_category[cat].append(skill.name)
                except Exception as e:
                    print(f"Warning: failed to load skill {skill_dir.name}: {e}")

    def reload(self):
        """Hot-reload skills (e.g. after adding to custom/)."""
        self.load_all()

    def get(self, name: str) -> Skill | None:
        return self._skills.get(name)

    def list_all(self) -> list[Skill]:
        return list(self._skills.values())

    def list_by_category(self, category: str) -> list[Skill]:
        names = self._by_category.get(category, [])
        return [self._skills[n] for n in names if n in self._skills]

    @property
    def summaries(self) -> str:
        """All skill summaries for Supervisor system prompt."""
        lines = []
        for skill in self._skills.values():
            lines.append(f"- {skill.name}: {skill.description}")
        return "\n".join(lines)

    @property
    def skill_names(self) -> list[str]:
        return list(self._skills.keys())

    def get_api_schema(self, skill_name: str, api_name: str) -> dict | None:
        """Get the parameter schema for a specific API of a skill."""
        skill = self.get(skill_name)
        if not skill:
            return None
        api = skill.get_api(api_name)
        if not api:
            return None
        return {
            "skill": skill_name,
            "api": api_name,
            "method": api.method,
            "description": api.description,
            "params": [{"name": p.name, "type": p.type, "required": p.required, "description": p.description} for p in api.params],
        }

    def call_api(self, skill_name: str, api_name: str, params: dict) -> dict:
        """Execute a mock API call and return the mock response."""
        skill = self.get(skill_name)
        if not skill:
            return {"error": f"Skill '{skill_name}' not found"}
        api = skill.get_api(api_name)
        if not api:
            return {"error": f"API '{api_name}' not found in skill '{skill_name}'"}
        result = dict(api.mock_response)
        result["_meta"] = {
            "skill": skill_name,
            "api": api_name,
            "called_with": params,
        }
        return result
