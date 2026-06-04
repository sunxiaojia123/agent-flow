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

        # Generate guidance text
        field_labels = [f["label"] for f in built_fields]
        guidance = f"请补充以下信息：{'、'.join(field_labels)}"

        return Command(
            goto="__end__",
            update={
                "final_action": "popup",
                "popup_message": message,
                "popup_fields": built_fields,
                "guidance_message": guidance,
                "messages": [AIMessage(content=guidance)],
            }
        )

    return formatter_popup_node


def create_formatter_card_node():
    def formatter_card_node(state: AgentState) -> Command:
        decision = state.get("supervisor_decision", {})
        card_type = state.get("card_type") or decision.get("card_type", "trade")
        card_data = state.get("card_data") or decision.get("card_data", {})

        # Generate guidance text based on card content
        recs = card_data.get("recommendations", [])
        summary = card_data.get("summary", {})
        if recs:
            supplier_names = "、".join(r.get("company_name", "") for r in recs[:2])
            guidance = f"根据查询结果，为您推荐 {supplier_names}，请查看下方卡片详情。"
        elif summary:
            product = summary.get("product", "产品")
            guidance = f"已为您找到 {product} 的采购方案，请查看下方卡片。"
        else:
            guidance = "已为您生成交易方案，请查看下方卡片。"

        return Command(
            goto="__end__",
            update={
                "final_action": "card",
                "card_type": card_type,
                "card_data": card_data,
                "guidance_message": guidance,
                "messages": [AIMessage(content=guidance)],
            }
        )

    return formatter_card_node
