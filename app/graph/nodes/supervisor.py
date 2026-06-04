"""Supervisor node — the sole reasoning brain with autonomous Reason-and-Action loop.

Supervisor receives available skill summaries and the full conversation history.
It handles everything: completeness checking, skill selection, API orchestration,
and final output routing. There is no separate Planner — Supervisor owns all decisions.

The loop: Supervisor → ToolNode → Supervisor (repeat until done).

Uses tool calling (bind_tools) instead of JSON mode for structured decisions.
Route tools (route_to_*) are intercepted by the supervisor — they never reach ToolNode.
Execution tools (get_user_context, load_skill_detail, call_api) are forwarded to ToolNode
via the supervisor_decision dict.
"""

import json
from langchain_core.messages import SystemMessage, AIMessage
from langgraph.types import Command
from app.graph.state import AgentState
from app.services.llm import get_llm

MAX_ITERATIONS = 15

# ── Tool definitions (OpenAI-compatible dicts for bind_tools) ──

ROUTE_TOOLS = [
    {
        "name": "route_to_formatter_text",
        "description": "以文字形式回复用户。当你已有足够信息、可以直接用文字回答时调用此工具。调用后当前处理循环结束。",
        "parameters": {
            "type": "object",
            "properties": {
                "message": {
                    "type": "string",
                    "description": "发送给用户的完整文字回复"
                },
                "reasoning": {
                    "type": "string",
                    "description": "为什么此时选择文字回复的推理过程"
                }
            },
            "required": ["message", "reasoning"]
        }
    },
    {
        "name": "route_to_formatter_popup",
        "description": "弹窗收集用户缺失信息。当你发现缺少关键参数（品类、数量、规格等）或需要用户确认选项时调用此工具。调用后当前处理循环结束。",
        "parameters": {
            "type": "object",
            "properties": {
                "message": {
                    "type": "string",
                    "description": "弹窗顶部显示的提示文字，解释需要用户补充什么信息"
                },
                "popup_fields": {
                    "type": "array",
                    "description": "弹窗表单字段列表",
                    "items": {
                        "type": "object",
                        "properties": {
                            "name": {"type": "string", "description": "字段标识符(snake_case)"},
                            "label": {"type": "string", "description": "显示给用户的字段标签"},
                            "type": {"type": "string", "enum": ["text", "number", "select"], "description": "text=自由输入, number=数字, select=下拉选择"},
                            "required": {"type": "boolean", "description": "是否必填"},
                            "options": {"type": "array", "items": {"type": "string"}, "description": "下拉选项(仅select类型)"},
                            "min": {"type": "number", "description": "最小值(仅number类型)"}
                        },
                        "required": ["name", "label", "type", "required"]
                    }
                },
                "reasoning": {
                    "type": "string",
                    "description": "为什么需要弹窗、缺失了什么信息的推理过程"
                }
            },
            "required": ["message", "popup_fields", "reasoning"]
        }
    },
    {
        "name": "route_to_formatter_card",
        "description": "展示结构化结果卡片。当数据已充分获取、可以生成交易推荐卡片或选商卡片时调用此工具。调用后当前处理循环结束。",
        "parameters": {
            "type": "object",
            "properties": {
                "card_type": {
                    "type": "string",
                    "enum": ["trade", "selection"],
                    "description": "trade=交易推荐卡片(含供应商/报价/物流), selection=选商卡片(多供应商对比)"
                },
                "card_data": {
                    "type": "object",
                    "description": "卡片数据。trade卡片需包含summary(product,quantity,unit)和recommendations数组(每项含company_name,city,unit_price,total_price,delivery_days,logistics_cost)。selection卡片含options数组。"
                },
                "reasoning": {
                    "type": "string",
                    "description": "为什么数据已充分、可以生成卡片的推理过程"
                }
            },
            "required": ["card_type", "card_data", "reasoning"]
        }
    },
]

EXECUTION_TOOLS = [
    {
        "name": "get_user_context",
        "description": "获取用户画像数据，包括偏好品类、默认地区、采购历史。仅在对话历史中找不到用户画像时才调用。",
        "parameters": {
            "type": "object",
            "properties": {
                "reasoning": {
                    "type": "string",
                    "description": "为什么需要获取用户画像的推理"
                }
            },
            "required": ["reasoning"]
        }
    },
    {
        "name": "load_skill_detail",
        "description": "加载指定供应商的完整信息（公司介绍、可用API列表、执行指南）。skill_name必须从「当前可用技能」列表中一字不差地复制，严禁编造不存在的技能名。",
        "parameters": {
            "type": "object",
            "properties": {
                "skill_name": {
                    "type": "string",
                    "description": "供应商技能名称，必须从可用技能列表中精确复制"
                },
                "reasoning": {
                    "type": "string",
                    "description": "为什么选择此供应商的推理"
                }
            },
            "required": ["skill_name", "reasoning"]
        }
    },
    {
        "name": "call_api",
        "description": "调用供应商API获取实时数据（库存/报价/物流等）。必须在load_skill_detail之后调用。常用API: check_inventory(查库存), get_quote(获取报价), check_logistics(查物流)。",
        "parameters": {
            "type": "object",
            "properties": {
                "skill_name": {
                    "type": "string",
                    "description": "供应商技能名称"
                },
                "api_name": {
                    "type": "string",
                    "description": "API名称，如check_inventory, get_quote, check_logistics"
                },
                "params": {
                    "type": "object",
                    "description": "API参数。check_inventory需product_category；get_quote需product_category,quantity；check_logistics需destination,quantity"
                },
                "reasoning": {
                    "type": "string",
                    "description": "为什么调用此API、预期获取什么数据的推理"
                }
            },
            "required": ["skill_name", "api_name", "reasoning"]
        }
    },
]

ALL_TOOLS = ROUTE_TOOLS + EXECUTION_TOOLS
ROUTE_NAME_PREFIX = "route_to_"
EXECUTION_TOOL_NAMES = {t["name"] for t in EXECUTION_TOOLS}

ROUTE_GOTO_MAP = {
    "route_to_formatter_text": "formatter_text",
    "route_to_formatter_popup": "formatter_popup",
    "route_to_formatter_card": "formatter_card",
}

# ── Helpers ──

def _tool_args_safe(raw_args) -> dict:
    """Defensively parse tool_call args into a dict."""
    if isinstance(raw_args, dict):
        return dict(raw_args)
    if isinstance(raw_args, str):
        try:
            return json.loads(raw_args)
        except (json.JSONDecodeError, TypeError):
            return {}
    return {}


def _build_route_decision(tool_name: str, tool_args: dict) -> dict:
    """Convert a route tool call into the supervisor_decision dict."""
    reasoning = tool_args.pop("reasoning", "")
    goto = ROUTE_GOTO_MAP[tool_name]
    decision = {"next": goto, "reasoning": reasoning}

    if goto == "formatter_text":
        decision["message"] = tool_args.get("message", "")
    elif goto == "formatter_popup":
        decision["message"] = tool_args.get("message", "请补充以下信息")
        decision["popup_fields"] = tool_args.get("popup_fields", [])
    elif goto == "formatter_card":
        decision["card_type"] = tool_args.get("card_type", "trade")
        decision["card_data"] = tool_args.get("card_data", {})

    return decision


def _build_execution_decision(tool_name: str, tool_args: dict, tool_call_id: str = "") -> dict:
    """Convert an execution tool call into the supervisor_decision dict.

    Pops 'reasoning' from tool_args so it doesn't leak into ToolNode.
    Includes tool_call_id so ToolNode can respond with a matching ToolMessage.
    """
    reasoning = tool_args.pop("reasoning", f"调用 {tool_name}")
    return {
        "next": "tools",
        "tool_name": tool_name,
        "tool_args": tool_args,
        "reasoning": reasoning,
        "tool_call_id": tool_call_id,
    }


# ── System Prompt ──

SUPERVISOR_SYSTEM_PROMPT = """你是交易系统的唯一中央决策大脑(Supervisor)。你运行在一个 Reason-and-Action 自治循环中，独揽从信息收集到最终输出的全部决策。

## 循环模式

每一轮你执行: 观察当前状态 → 推理分析 → 调用工具 → 工具执行 → 结果返回给你 → 再次推理
这个循环持续进行，直到你判断信息充分、可以给用户最终答案时，调用路由工具结束循环。

## 可用工具

路由工具（终止循环并输出结果给用户）:
- **route_to_formatter_text**: 以文字形式回复用户
- **route_to_formatter_popup**: 弹窗收集缺失信息（品类/数量/规格等）
- **route_to_formatter_card**: 展示结构化结果卡片（交易推荐/选商对比）

执行工具（获取数据后继续循环）:
- **get_user_context**: 获取用户画像、采购历史、偏好品类和地区
- **load_skill_detail**: 加载指定供应商的完整信息（公司介绍、API列表、执行指南）
- **call_api**: 调用供应商API获取实时数据（库存/报价/物流等）

## 决策原则

你是"最强大脑"，拥有做出所有决策所需的全部信息。请根据实际情况自主决策:

1. **第一轮: 读取历史 + 缺失补全**: 先检查对话历史中是否已有 `get_user_context` 返回的用户画像。如果已有（弹窗后继续的场景），直接基于画像和弹窗回复继续决策，**不要重复获取画像**。只有在对话历史中找不到画像数据时，才调用 `get_user_context`。获取画像后，综合用户历史消息和画像信息判断:
   - 产品品类是否明确? (用户说了 or 画像有默认偏好)
   - 采购数量是否明确?
   - 所在地区是否明确? (用户说了 or 画像有默认地区)
   - 如果关键信息不全，**立即调用 route_to_formatter_popup** 收集缺失信息，不要继续调用其他工具浪费资源。
   - 如果信息完整，继续下一步。

2. **按需加载**: 信息完整后，只加载与用户需求相关的供应商技能。通常1-2个最匹配的即可。**技能名必须从「当前可用技能」列表中一字不差地复制**，严禁自行编造不存在的技能名。

3. **数据驱动**: 调用API获取真实数据。拿到库存→获取报价，拿到报价→考虑查物流，信息充分→结束。

4. **灵活应变**: 如果某个供应商库存不足或数据不佳，换另一个供应商。根据实际数据调整策略。

5. **适时终止**: 信息足够支撑结论时果断调用路由工具结束——不要无意义地继续循环。

6. **每次只调用一个工具**: 一次只能调用一个工具。需要多个API时，逐个调用。

7. **弹窗是正常交互**: 执行过程中发现需要更多信息时，自然地调用 route_to_formatter_popup 收集。这不是异常兜底，而是正常的业务流程。

## 使用指南

- 每次只调用一个工具。即使需要多个API，也逐个调用。
- 路由工具会终止当前循环并输出结果给用户。执行工具会返回数据并继续循环。
- 信息充分时果断调用路由工具结束循环。信息不足时果断调用 route_to_formatter_popup 收集。
- 不要输出文字，直接调用工具。
"""


# ── Node factory ──

def create_supervisor_node(get_summaries):
    """Create the Supervisor node — the sole reasoning brain.

    Uses tool calling (bind_tools) for structured decisions instead of JSON mode.
    Route tools are intercepted here; execution tools are forwarded to ToolNode
    via the supervisor_decision dict.
    """
    llm = get_llm(temperature=0.0)
    bound_llm = llm.bind_tools(ALL_TOOLS, tool_choice="required")

    def supervisor_node(state: AgentState) -> Command:
        summaries = get_summaries()
        iteration = state.get("iteration_count", 0) + 1

        # ---- Build system prompt with dynamic context ----
        context_parts = [SUPERVISOR_SYSTEM_PROMPT]

        # Inject available skills
        context_parts.append(f"\n## 当前可用技能\n{summaries}")

        # Iteration counter
        context_parts.append(f"\n## 循环计数: {iteration}/{MAX_ITERATIONS}")
        if iteration >= MAX_ITERATIONS:
            context_parts.append(
                "⚠️ 已达到最大循环次数。本轮必须调用路由工具结束循环，"
                "不得再选择执行工具。"
            )

        prompt = "\n".join(context_parts)

        # ---- Build message list ----
        all_msgs = list(state["messages"])
        # Filter + sanitize message history.
        # - Remove old-format supervisor JSON prose (backward compat).
        # - Sanitize any AIMessage with tool_calls: DeepSeek may include raw
        #   formatting (e.g. <|tool_calls_section_begin|>...) in content.
        #   Clear content but KEEP tool_calls — ToolMessage pairing requires
        #   a preceding AIMessage with matching tool_calls.
        filtered_msgs = []
        for m in all_msgs:
            if isinstance(m, AIMessage) and getattr(m, 'name', None) == 'supervisor':
                continue
            if isinstance(m, AIMessage) and getattr(m, 'tool_calls', None):
                # Only keep the first tool_call — we only ever execute one.
                # Multiple tool_calls with <N ToolMessages → 400 error.
                tc = m.tool_calls
                m = AIMessage(content="", tool_calls=tc[:1], id=m.id)
            filtered_msgs.append(m)

        # Status injection
        last_decision = state.get("supervisor_decision", {})
        if last_decision:
            last_goto = last_decision.get("next", "")
            last_tool = last_decision.get("tool_name", "")
            last_reasoning = last_decision.get("reasoning", "")
            status = f"[状态] 上一轮: → {last_goto}"
            if last_tool:
                status += f" | 工具: {last_tool}"
            if last_reasoning:
                status += f" | 原因: {last_reasoning}"
            filtered_msgs.insert(0, SystemMessage(content=status))

        recent_msgs = filtered_msgs[-30:] if len(filtered_msgs) > 30 else filtered_msgs
        messages = [SystemMessage(content=prompt)] + recent_msgs

        # ---- LLM call with tool calling ----
        try:
            response = bound_llm.invoke(messages)
        except Exception as e:
            # If tool calling is not supported by the provider, fall back gracefully
            error_msg = str(e)
            decision = {
                "next": "formatter_text",
                "message": "抱歉，处理过程中遇到问题，请重新描述您的需求。",
                "reasoning": f"LLM调用失败: {error_msg[:200]}",
            }
            return Command(goto="formatter_text", update={
                "supervisor_decision": decision,
                "iteration_count": iteration,
                "final_action": "text",
                "messages": [AIMessage(content=decision["message"])],
            })

        tool_calls = getattr(response, "tool_calls", None) or []

        # ---- Retry once if no tool_call ----
        if not tool_calls:
            retry_prompt = (
                prompt
                + "\n\n## ⚠️ 必须调用工具\n"
                + "你上一轮没有调用任何工具。你必须从可用工具中选择一个:\n"
                + "- 已有足够信息回复用户 → route_to_formatter_text\n"
                + "- 需要向用户收集信息 → route_to_formatter_popup\n"
                + "- 已有完整数据展示结果 → route_to_formatter_card\n"
                + "- 需要更多数据 → get_user_context / load_skill_detail / call_api\n"
                + "不要输出文字，直接调用一个工具。"
            )
            retry_messages = [SystemMessage(content=retry_prompt)] + recent_msgs
            try:
                response = bound_llm.invoke(retry_messages)
            except Exception:
                response = None
            tool_calls = getattr(response, "tool_calls", None) or [] if response else []

        # ---- Process tool_call or fallback ----
        if tool_calls:
            tool_call = tool_calls[0]
            tool_name = tool_call.get("name", "")
            raw_args = tool_call.get("args", {})
            tool_args = _tool_args_safe(raw_args)
            tc_id = tool_call.get("id", "")

            if tool_name.startswith(ROUTE_NAME_PREFIX):
                # Route tool — intercepted here, forwarded to formatter
                decision = _build_route_decision(tool_name, tool_args)
                goto = decision["next"]
            elif tool_name in EXECUTION_TOOL_NAMES:
                # Execution tool — routed through ToolNode with tool_call_id
                decision = _build_execution_decision(tool_name, tool_args, tc_id)
                goto = "tools"
            else:
                # Unknown tool — fallback (should not happen with bind_tools)
                decision = {
                    "next": "formatter_text",
                    "message": f"未知工具: {tool_name}",
                    "reasoning": f"LLM调用了未注册的工具: {tool_name}",
                }
                goto = "formatter_text"
        else:
            # Double fallback: no tool calls after retry
            fallback_msg = (
                (getattr(response, "content", "") or "").strip()
                or "抱歉，处理过程中遇到问题，请重新描述您的需求。"
            )
            decision = {
                "next": "formatter_text",
                "message": fallback_msg[:500],
                "reasoning": "两次调用均未产生工具调用，强制终止",
            }
            goto = "formatter_text"

        # ---- Safety: force termination at max iterations ----
        if iteration >= MAX_ITERATIONS and goto == "tools":
            goto = "formatter_text"
            decision["next"] = "formatter_text"
            if not decision.get("message"):
                decision["message"] = "已达到最大处理步骤，以下是根据当前数据的结果汇总。"
            decision["reasoning"] = (
                decision.get("reasoning", "") + " [达到最大迭代次数，强制终止]"
            )

        # ---- Build state update ----
        # For execution tools: store raw response with tool_calls — ToolNode
        # follows up with a ToolMessage matching the tool_call_id. Correct pairing.
        # For route tools: store a clean AIMessage without tool_calls —
        # route tools bypass ToolNode, so no ToolMessage follows. An unmatched
        # tool_calls entry would break the API on the next request.
        if goto == "tools":
            # Store only the tool_call we actually executed. If the LLM returns
            # multiple tool_calls, storing all of them would violate the API
            # contract: ToolNode only produces ONE ToolMessage, so N tool_calls
            # with <N ToolMessages → "insufficient tool messages" 400 error.
            msg_for_history = AIMessage(
                content="",
                tool_calls=[tool_call],
                id=response.id,
            )
        else:
            msg_for_history = AIMessage(content=decision.get("reasoning", ""))

        update: dict = {
            "supervisor_decision": decision,
            "iteration_count": iteration,
            "messages": [msg_for_history],
        }

        # Bridge formatter data into state
        if goto == "formatter_text":
            update["final_action"] = "text"
        elif goto == "formatter_popup":
            update["final_action"] = "popup"
            update["popup_message"] = decision.get("message", "请补充以下信息")
            update["popup_fields"] = decision.get("popup_fields", [])
        elif goto == "formatter_card":
            update["final_action"] = "card"
            update["card_type"] = decision.get("card_type", "trade")
            update["card_data"] = decision.get("card_data", {})

        return Command(goto=goto, update=update)

    return supervisor_node
