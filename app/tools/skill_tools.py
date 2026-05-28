"""Skill-related tools: load_skill_detail, get_api_schema."""

from app.skills.registry import SkillRegistry

_registry: SkillRegistry | None = None


def set_registry(registry: SkillRegistry):
    global _registry
    _registry = registry


def load_skill_detail(skill_name: str) -> dict:
    """Load the full SKILL.md content for a skill. Returns company info, APIs, and execution guide."""
    if not _registry:
        return {"error": "Registry not initialized"}
    skill = _registry.get(skill_name)
    if not skill:
        return {"error": f"Skill '{skill_name}' not found"}

    apis_summary = []
    for api in skill.apis:
        params_desc = ", ".join(
            f"{p.name}({p.type}{'必填' if p.required else '可选'})"
            for p in api.params
        )
        apis_summary.append(f"- {api.name} [{api.method}]: {api.description} | 参数: {params_desc or '无'}")

    return {
        "skill_name": skill.name,
        "display_name": skill.display_name,
        "description": skill.description,
        "category": skill.category,
        "company_info": skill.company_info,
        "apis": apis_summary,
        "execution_guide": skill.execution_guide,
        "_next_action": "请立即使用 call_api 调用此skill的API获取真实数据。例如先调 check_inventory 查库存。不要直接跳到formatter，formatter只有在拿到API返回数据后才能使用。",
    }


def get_api_schema(skill_name: str, api_name: str) -> dict:
    """Get the parameter schema for a specific API endpoint of a skill."""
    if not _registry:
        return {"error": "Registry not initialized"}
    return _registry.get_api_schema(skill_name, api_name) or {
        "error": f"API '{api_name}' not found in skill '{skill_name}'"
    }
