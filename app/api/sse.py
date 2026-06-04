"""SSE event generator — streams LangGraph execution as rich SSE events.

Event types:
- meta:        node lifecycle (start/end) and phase transitions
- thinking:    supervisor reasoning step (what to do next)
- progress:    tool execution progress (loading skill, calling API, etc.)
- text_delta:  streaming text chunks for user-visible output
- text_done:   text stream complete
- popup:       structured popup form for collecting user input
- card:        structured card for displaying results (trade/selection)
- done:        conversation complete
- error:       error occurred
"""

import json
import uuid
from langgraph.types import Command

NODE_LABELS = {
    "coordinator": "正在分析您的意图...",
    "supervisor": "Supervisor 正在决策...",
    "tools": "正在执行工具...",
    "formatter_text": "正在生成回复...",
    "formatter_popup": "正在收集信息...",
    "formatter_card": "正在生成结果卡片...",
}

# Human-readable descriptions for tool calls
TOOL_DISPLAY = {
    "get_user_context": "获取用户画像",
    "load_skill_detail": "加载技能详情",
    "get_api_schema": "获取API参数定义",
    "call_api": "调用API",
}

API_DISPLAY = {
    "check_inventory": "查询库存",
    "get_quote": "获取报价",
    "check_logistics": "查询物流",
    "get_profile": "获取用户信息",
    "get_history": "获取采购历史",
}


def format_sse(event: str, data: dict) -> str:
    lines = [
        f"event: {event}",
        f"data: {json.dumps(data, ensure_ascii=False)}",
    ]
    return "\n".join(lines) + "\n\n"


def _build_tool_message(tool_name: str, tool_args: dict) -> str:
    """Build a human-readable message describing what tool is being called."""
    display = TOOL_DISPLAY.get(tool_name, tool_name)

    if tool_name == "call_api":
        skill = tool_args.get("skill_name", "")
        api = tool_args.get("api_name", "")
        api_display = API_DISPLAY.get(api, api)
        return f"{display}: {api_display}"

    if tool_name == "load_skill_detail":
        skill = tool_args.get("skill_name", "")
        return f"{display}: {skill}"

    if tool_name == "get_user_context":
        return "获取用户画像和采购偏好"

    return display


def _summarize_tool_result(tool_name: str, message_content: str) -> str:
    """Build a concise summary of tool execution result."""
    # Strip the [ToolNode: ...] prefix if present
    json_start = message_content.find('{')
    json_str = message_content[json_start:] if json_start != -1 else message_content

    try:
        data = json.loads(json_str)
    except (json.JSONDecodeError, TypeError):
        return message_content[:80]

    if isinstance(data, dict):
        if "error" in data:
            return f"失败: {data['error']}"
        if tool_name == "get_user_context":
            profile = data.get("profile", {})
            name = profile.get("name", "")
            city = profile.get("default_city", "")
            prefs = profile.get("preferred_categories", [])
            return f"用户: {name}, 地区: {city}, 偏好: {', '.join(prefs) if prefs else '无'}"
        if tool_name == "load_skill_detail":
            name = data.get("display_name", data.get("skill_name", ""))
            api_count = len(data.get("apis", []))
            return f"已加载 {name}, {api_count} 个API可用"
        if tool_name == "call_api":
            meta = data.get("_meta", {})
            api = meta.get("api", "")
            api_display = API_DISPLAY.get(api, api)
            # Extract key data points
            if "stock" in data:
                return f"{api_display}: 库存 {data['stock']} {data.get('unit', '吨')}"
            if "unit_price" in data:
                return f"{api_display}: {data['unit_price']} 元/吨, 总价 {data.get('total_price', '?')} 元"
            if "logistics_cost" in data:
                return f"{api_display}: {data.get('delivery_time', '?')}天, 运费 {data['logistics_cost']} 元"
            return f"{api_display}: 完成"
    return str(data)[:80]


async def sse_event_generator(graph, input_state: dict, config: dict):
    """Yields SSE events from LangGraph astream_events."""
    conv_id = config["configurable"]["thread_id"]
    span_id = str(uuid.uuid4())[:8]
    last_supervisor_decision = None

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

            # ── Node start ──
            if kind == "on_chain_start" and name in NODE_LABELS:
                label = NODE_LABELS[name]

                # Tools node start: emit progress with tool info
                if name == "tools" and last_supervisor_decision:
                    tool_name = last_supervisor_decision.get("tool_name", "")
                    tool_args = last_supervisor_decision.get("tool_args", {})
                    progress_msg = _build_tool_message(tool_name, tool_args)
                    yield format_sse("progress", {
                        "type": "progress",
                        "phase": "tool_start",
                        "tool_name": tool_name,
                        "tool_args": tool_args,
                        "message": progress_msg,
                        "span_id": span_id,
                    })

                yield format_sse("meta", {
                    "type": "meta",
                    "node": name,
                    "message": label,
                    "status": "start",
                    "span_id": span_id,
                })

            # ── LLM streaming (text nodes only) ──
            elif kind == "on_chat_model_stream":
                if name in ("formatter_text",):
                    chunk = event["data"]["chunk"]
                    if hasattr(chunk, "content") and chunk.content:
                        if isinstance(chunk.content, str) and chunk.content.strip():
                            yield format_sse("text_delta", {
                                "type": "text_delta",
                                "content": chunk.content,
                            })

            # ── Node end ──
            elif kind == "on_chain_end" and name in NODE_LABELS:
                yield format_sse("meta", {
                    "type": "meta",
                    "node": name,
                    "message": NODE_LABELS[name],
                    "status": "end",
                    "span_id": span_id,
                })

                # Extract output data
                raw_output = event.get("data", {}).get("output", {})
                if isinstance(raw_output, Command):
                    output = raw_output.update or {}
                elif isinstance(raw_output, dict):
                    output = raw_output
                else:
                    output = {}

                if not isinstance(output, dict):
                    continue

                # ── Supervisor end: emit thinking event ──
                if name == "supervisor":
                    decision = output.get("supervisor_decision", {})
                    if decision:
                        last_supervisor_decision = decision
                        next_step = decision.get("next", "")
                        tool_name = decision.get("tool_name", "")
                        reasoning = decision.get("reasoning", "")

                        yield format_sse("thinking", {
                            "type": "thinking",
                            "reasoning": reasoning,
                            "next_action": next_step,
                            "tool_name": tool_name,
                            "tool_args": decision.get("tool_args", {}),
                            "span_id": span_id,
                        })

                        # Also keep the existing meta for backward compat
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
                                "reasoning": reasoning,
                                "message": f"Supervisor → {next_step}",
                                "span_id": span_id,
                            })

                # ── Tools end: emit progress with result summary ──
                if name == "tools" and last_supervisor_decision:
                    tool_name = last_supervisor_decision.get("tool_name", "")
                    msgs = output.get("messages", [])
                    result_text = ""
                    for m in msgs:
                        if hasattr(m, "content") and m.content:
                            result_text = m.content
                            break
                    summary = _summarize_tool_result(tool_name, result_text)

                    yield format_sse("progress", {
                        "type": "progress",
                        "phase": "tool_end",
                        "tool_name": tool_name,
                        "message": summary,
                        "span_id": span_id,
                    })

                # ── Formatter text end: emit text from messages ──
                if name == "formatter_text":
                    msgs = output.get("messages", [])
                    for m in msgs:
                        if hasattr(m, "content") and m.content:
                            if hasattr(m, "name") and m.name in ("supervisor",):
                                continue
                            content = m.content
                            if isinstance(content, str) and content.strip():
                                # Stream the entire text as completed chunks
                                yield format_sse("text_delta", {
                                    "type": "text_delta",
                                    "content": content,
                                })

                # ── Formatter popup end: text guidance first, then popup ──
                if name == "formatter_popup":
                    guidance = output.get("guidance_message", "")
                    popup_fields = output.get("popup_fields", [])
                    popup_message = output.get("popup_message", "请补充以下信息")

                    # Emit guidance as streaming text
                    if guidance:
                        yield format_sse("text_delta", {
                            "type": "text_delta",
                            "content": guidance,
                        })
                    yield format_sse("text_done", {"type": "text_done"})

                    # Then emit popup event
                    if popup_fields:
                        yield format_sse("popup", {
                            "type": "popup",
                            "popup_id": str(uuid.uuid4()),
                            "fields": popup_fields,
                            "message": popup_message,
                        })

                # ── Formatter card end: text guidance first, then card ──
                if name == "formatter_card":
                    guidance = output.get("guidance_message", "")
                    card_type = output.get("card_type", "trade")
                    card_data = output.get("card_data", {})

                    # Emit guidance as streaming text
                    if guidance:
                        yield format_sse("text_delta", {
                            "type": "text_delta",
                            "content": guidance,
                        })
                    yield format_sse("text_done", {"type": "text_done"})

                    # Then emit card event
                    if card_data:
                        yield format_sse("card", {
                            "type": "card",
                            "card_type": card_type,
                            "data": card_data,
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
