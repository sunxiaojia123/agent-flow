"""Router type definitions for Supervisor structured output."""

from typing import Literal, Optional
from typing_extensions import TypedDict


class Router(TypedDict, total=False):
    """Supervisor routing decision schema (structured output)."""
    next: Literal["tools", "formatter_text", "formatter_popup", "formatter_card"]
    tool_name: Optional[str]       # for "tools": load_skill_detail | get_api_schema | call_api | get_user_context
    tool_args: Optional[dict]      # e.g. {"skill_name": "shagang-supplier"}
    message: Optional[str]         # for formatter_text / formatter_popup
    popup_fields: Optional[list]   # for formatter_popup
    card_type: Optional[str]       # for formatter_card: "trade" | "selection"
    card_data: Optional[dict]      # for formatter_card
    reasoning: str                 # always required for debugging


class Plan(TypedDict):
    """Planner output schema."""
    thought: str
    steps: list[dict]
