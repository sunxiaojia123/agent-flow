"""Agent state — central data structure flowing through the graph."""

from typing import Annotated, Optional
from typing_extensions import TypedDict
from langgraph.graph.message import add_messages


class AgentState(TypedDict):
    messages: Annotated[list, add_messages]
    conversation_id: str
    plan: Optional[dict]                # [已废弃] Planner 已移除，保留字段兼容，始终为 None
    supervisor_decision: Optional[dict] # Latest Supervisor Router output
    coordinator_reply: Optional[str]    # Coordinator's direct reply (for chitchat)
    final_action: str                   # "text" | "popup" | "card" | ""
    popup_message: str                  # ask_user popup message
    popup_fields: list[dict]            # ask_user field definitions
    card_type: str                      # "trade" | "selection"
    card_data: dict                     # card payload
    iteration_count: int                # Supervisor loop iteration counter (safety guard)
    guidance_message: str               # text guidance emitted before popup/card events
