"""API execution tool: call_api (mock)."""

from app.skills.registry import SkillRegistry

_registry: SkillRegistry | None = None


def set_registry(registry: SkillRegistry):
    global _registry
    _registry = registry


def call_api(skill_name: str, api_name: str, params: dict) -> dict:
    """Execute a mock API call against a supplier skill. Returns the mock response defined in SKILL.md."""
    if not _registry:
        return {"error": "Registry not initialized"}
    return _registry.call_api(skill_name, api_name, params)
