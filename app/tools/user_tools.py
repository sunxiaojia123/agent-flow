"""User context tool: get_user_context."""

from app.skills.registry import SkillRegistry

_registry: SkillRegistry | None = None


def set_registry(registry: SkillRegistry):
    global _registry
    _registry = registry


def get_user_context() -> dict:
    """Load the user profile skill and return user info + purchase history."""
    if not _registry:
        return {"error": "Registry not initialized"}

    profile = _registry.call_api("user-profile", "get_profile", {})
    history = _registry.call_api("user-profile", "get_history", {})

    return {
        "profile": profile,
        "purchase_history": history,
    }
