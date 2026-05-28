"""SSE event generator — streams LangGraph execution as SSE events."""

import json
import uuid
from langgraph.types import Command


NODE_LABELS = {
    "coordinator": "正在分析您的意图...",
    "planner": "正在制定执行计划...",
    "supervisor": "Supervisor 正在决策...",
    "tools": "正在执行工具...",
    "formatter_text": "正在生成回复...",
    "formatter_popup": "正在收集信息...",
    "formatter_card": "正在生成结果卡片...",
}

NODE_ORDER = [
    "coordinator", "planner", "supervisor", "tools",
    "formatter_text", "formatter_popup", "formatter_card",
]


def format_sse(event: str, data: dict) -> str:
    lines = [
        f"event: {event}",
        f"data: {json.dumps(data, ensure_ascii=False)}",
    ]
    return "\n".join(lines) + "\n\n"


async def sse_event_generator(graph, input_state: dict, config: dict):
    """Yields SSE events from LangGraph astream_events."""
    conv_id = config["configurable"]["thread_id"]
    current_node = None
    span_id = str(uuid.uuid4())[:8]

    yield format_sse("meta", {
        "type": "meta",
        "conversation_id": conv_id,
        "node": "START",
        "message": "开始处理...",
        "span_id": span_id,
    })

    try:
        async for event in graph.astream_events(input_state, config, version="v2"):
            kind = event["event"]
            name = event.get("name", "")

            # Node start
            if kind == "on_chain_start" and name in NODE_LABELS:
                current_node = name

                # Special handling for tools node - include tool name
                tool_meta = {}
                if name == "tools":
                    # Tool info will be in the previous supervisor_decision
                    pass

                yield format_sse("meta", {
                    "type": "meta",
                    "node": name,
                    "message": NODE_LABELS[name],
                    "status": "start",
                    "span_id": span_id,
                    **tool_meta,
                })

            # LLM streaming (text nodes only)
            elif kind == "on_chat_model_stream":
                if current_node in ("formatter_text",):
                    chunk = event["data"]["chunk"]
                    if hasattr(chunk, "content") and chunk.content:
                        if isinstance(chunk.content, str) and chunk.content.strip():
                            yield format_sse("text_delta", {
                                "type": "text_delta",
                                "content": chunk.content,
                            })

            # Node end
            elif kind == "on_chain_end" and name in NODE_LABELS:
                yield format_sse("meta", {
                    "type": "meta",
                    "node": name,
                    "message": NODE_LABELS[name],
                    "status": "end",
                    "span_id": span_id,
                })

                # After a node ends, check for special outputs
                raw_output = event.get("data", {}).get("output", {})
                # Command objects: extract the update dict
                if isinstance(raw_output, Command):
                    output = raw_output.update or {}
                elif isinstance(raw_output, dict):
                    output = raw_output
                else:
                    output = {}
                if isinstance(output, dict):
                    # After supervisor ends, emit decision info
                    if name == "supervisor":
                        decision = output.get("supervisor_decision", {})
                        if decision:
                            next_step = decision.get("next", "")
                            tool_name = decision.get("tool_name", "")
                            if next_step == "tools" and tool_name:
                                yield format_sse("meta", {
                                    "type": "meta",
                                    "phase": "tool_planned",
                                    "tool_name": tool_name,
                                    "tool_args": decision.get("tool_args", {}),
                                    "message": f"Supervisor → 调用 {tool_name}",
                                    "span_id": span_id,
                                })
                            elif next_step and next_step.startswith("formatter"):
                                yield format_sse("meta", {
                                    "type": "meta",
                                    "phase": "supervisor_end",
                                    "next": next_step,
                                    "reasoning": decision.get("reasoning", ""),
                                    "message": f"Supervisor → {next_step}",
                                    "span_id": span_id,
                                })

                    # After formatter_text ends, emit text from messages
                    if name == "formatter_text":
                        msgs = output.get("messages", [])
                        for m in msgs:
                            if hasattr(m, "content") and m.content:
                                # Skip internal messages (Supervisor/Planner)
                                if hasattr(m, "name") and m.name in ("supervisor", "planner"):
                                    continue
                                content = m.content
                                if isinstance(content, str) and content.strip():
                                    yield format_sse("text_delta", {
                                        "type": "text_delta",
                                        "content": content,
                                    })
                    if name == "formatter_card":
                        card_type = output.get("card_type", "trade")
                        card_data = output.get("card_data", {})
                        if card_data:
                            yield format_sse("card", {
                                "type": "card",
                                "card_type": card_type,
                                "data": card_data,
                            })

                    # After formatter_popup ends, emit popup event
                    if name == "formatter_popup":
                        popup_fields = output.get("popup_fields", [])
                        popup_message = output.get("popup_message", "请补充以下信息")
                        if popup_fields:
                            yield format_sse("popup", {
                                "type": "popup",
                                "popup_id": str(uuid.uuid4()),
                                "fields": popup_fields,
                                "message": popup_message,
                            })

        yield format_sse("text_done", {"type": "text_done"})
        yield format_sse("done", {
            "type": "done",
            "conversation_id": conv_id,
        })

    except Exception as e:
        yield format_sse("error", {
            "type": "error",
            "code": "INTERNAL_ERROR",
            "message": str(e),
        })
        yield format_sse("done", {
            "type": "done",
            "conversation_id": conv_id,
        })
