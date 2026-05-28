"""Formatter nodes — generate final output events (text / popup / card)."""

from langchain_core.messages import AIMessage
from langgraph.types import Command
from app.graph.state import AgentState


def create_formatter_text_node():
    def formatter_text_node(state: AgentState) -> Command:
        reply = state.get("coordinator_reply", "")
        if not reply:
            decision = state.get("supervisor_decision", {})
            reply = decision.get("message", "")
        if not reply:
            # Fallback: use reasoning or a default message
            decision = state.get("supervisor_decision", {})
            reply = decision.get("reasoning", "处理完成，请查看结果。")

        if reply:
            return Command(
                goto="__end__",
                update={
                    "final_action": "text",
                    "messages": [AIMessage(content=reply)],
                }
            )
        return Command(goto="__end__", update={"final_action": "text"})

    return formatter_text_node


def create_formatter_popup_node():
    def formatter_popup_node(state: AgentState) -> Command:
        decision = state.get("supervisor_decision", {})
        message = state.get("popup_message") or decision.get("message", "请补充以下信息")
        fields = state.get("popup_fields") or decision.get("popup_fields", [])

        # Build structured popup fields
        built_fields = []
        for f in fields:
            field = {
                "name": f.get("name", ""),
                "label": f.get("label", f.get("name", "")),
                "type": f.get("type", "text"),
                "required": True,
            }
            if f.get("options"):
                field["options"] = f["options"]
            if f.get("type") == "number":
                field["min"] = f.get("min", 1)
            built_fields.append(field)

        return Command(
            goto="__end__",
            update={
                "final_action": "popup",
                "popup_message": message,
                "popup_fields": built_fields,
                "messages": [AIMessage(content=f"[弹窗] {message}")],
            }
        )

    return formatter_popup_node


def create_formatter_card_node():
    def formatter_card_node(state: AgentState) -> Command:
        decision = state.get("supervisor_decision", {})
        card_type = state.get("card_type") or decision.get("card_type", "trade")
        card_data = state.get("card_data") or decision.get("card_data", {})

        return Command(
            goto="__end__",
            update={
                "final_action": "card",
                "card_type": card_type,
                "card_data": card_data,
                "messages": [AIMessage(content=f"[卡片: {card_type}]")],
            }
        )

    return formatter_card_node
