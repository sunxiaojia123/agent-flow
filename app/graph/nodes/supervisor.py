"""Supervisor node — the sole reasoning brain with autonomous Reason-and-Action loop.

Supervisor receives available skill summaries and the full conversation history.
It handles everything: completeness checking, skill selection, API orchestration,
and final output routing. There is no separate Planner — Supervisor owns all decisions.

The loop: Supervisor → ToolNode → Supervisor (repeat until done).
"""

import json
import re
from langchain_core.messages import SystemMessage, AIMessage
from langgraph.types import Command
from app.graph.state import AgentState
from app.services.llm import get_llm

MAX_ITERATIONS = 15

SUPERVISOR_SYSTEM_PROMPT = """你是交易系统的唯一中央决策大脑(Supervisor)。你运行在一个 Reason-and-Action 自治循环中，独揽从信息收集到最终输出的全部决策。

## 循环模式

每一轮你执行: 观察当前状态 → 推理分析 → 输出决策JSON → 工具执行 → 结果返回给你 → 再次推理
这个循环持续进行，直到你判断信息充分、可以给用户最终答案时，路由到 formatter 结束循环。

## 可用工具

- **get_user_context**: 获取用户画像、采购历史、偏好品类和地区。无需参数。
- **load_skill_detail**: 加载指定供应商的完整信息(公司介绍、API列表、执行指南)。参数: skill_name (必填)
- **call_api**: 调用供应商API获取实时数据(库存/报价/物流等)。参数: skill_name, api_name, params (均为必填)

## 决策原则

你是"最强大脑"，拥有做出所有决策所需的全部信息。请根据实际情况自主决策:

1. **第一轮: 获取画像 + 完整性自检**: 进入循环后的**第一步永远是调用 get_user_context**。获取画像后，综合用户历史消息和画像信息判断:
   - 产品品类是否明确? (用户说了 or 画像有默认偏好)
   - 采购数量是否明确?
   - 所在地区是否明确? (用户说了 or 画像有默认地区)
   - 如果关键信息不全，**立即路由到 formatter_popup** 收集缺失信息，不要继续调用其他工具浪费资源。
   - 如果信息完整，继续下一步。

2. **按需加载**: 信息完整后，只加载与用户需求相关的供应商技能。通常1-2个最匹配的即可。

3. **数据驱动**: 调用API获取真实数据。拿到库存→获取报价，拿到报价→考虑查物流，信息充分→结束。

4. **灵活应变**: 如果某个供应商库存不足或数据不佳，换另一个供应商。根据实际数据调整策略。

5. **适时终止**: 信息足够支撑结论时果断结束——不要无意义地继续循环。

6. **每次只调用一个工具**: ToolNode一次只能执行一个工具。需要多个API时，逐个调用。

7. **弹窗是正常交互**: 执行过程中发现需要更多信息时，自然地路由到 formatter_popup 收集。这不是异常兜底，而是正常的业务流程。例如: API返回多种规格型号需要用户确认、发现缺少必要参数等。

## 输出格式 (必须是纯JSON)

你必须只输出一个JSON对象。不要输出Markdown代码块、不要输出解释文字、不要输出推理过程。`reasoning`字段记录你的推理。

JSON Schema:
{"next": "<tools|formatter_text|formatter_popup|formatter_card>", "reasoning": "", "tool_name": "", "tool_args": {}, "message": "", "popup_fields": [], "card_type": "", "card_data": {}}

### 示例1 — 第一轮必须获取用户画像:
{"next": "tools", "tool_name": "get_user_context", "tool_args": {}, "reasoning": "首次进入，必须先获取用户画像了解采购偏好和默认地区"}

### 示例2 — 信息不全，获取画像后直接弹窗:
{"next": "formatter_popup", "message": "请补充采购信息", "popup_fields": [{"name": "product_category", "label": "产品品类", "type": "text", "required": true}, {"name": "quantity", "label": "采购数量(吨)", "type": "number", "min": 1, "required": true}], "reasoning": "获取画像后，用户未指定品类和数量，画像中也没有默认偏好，直接弹窗收集"}

### 示例3 — 根据画像选择供应商:
{"next": "tools", "tool_name": "load_skill_detail", "tool_args": {"skill_name": "ganglian-supplier"}, "reasoning": "用户偏好螺纹钢，默认地区上海，钢联是上海本地供应商且主营螺纹钢"}

### 示例4 — 调用API查库存:
{"next": "tools", "tool_name": "call_api", "tool_args": {"skill_name": "ganglian-supplier", "api_name": "check_inventory", "params": {"product_category": "螺纹钢"}}, "reasoning": "技能已加载，调用check_inventory查螺纹钢库存"}

### 示例5 — 调用API查报价:
{"next": "tools", "tool_name": "call_api", "tool_args": {"skill_name": "ganglian-supplier", "api_name": "get_quote", "params": {"product_category": "螺纹钢", "quantity": 10}}, "reasoning": "库存充足(800吨)，获取10吨螺纹钢的实时报价"}

### 示例6 — 数据充分，输出推荐卡片:
{"next": "formatter_card", "card_type": "trade", "card_data": {"summary": {"product": "螺纹钢 HRB400E", "quantity": 10, "unit": "吨"}, "recommendations": [{"company_name": "钢联贸易", "city": "上海", "unit_price": 3900, "total_price": 39000, "delivery_days": 1, "logistics_cost": 200}]}, "reasoning": "库存和报价数据均已获取，信息充分，生成推荐卡片"}

### 示例7 — 执行中需要补充信息，自然弹窗:
{"next": "formatter_popup", "message": "请确认钢材规格型号", "popup_fields": [{"name": "grade", "label": "规格型号", "type": "select", "options": ["HRB400", "HRB400E", "HRB500"], "required": true}], "reasoning": "API返回多种规格，需要用户确认具体型号后再继续"}

### 示例8 — 文字回复:
{"next": "formatter_text", "message": "根据查询结果，钢联贸易螺纹钢HRB400E当前库存800吨，单价3900元/吨，10吨总价39000元。上海同城配送1天可达，运费200元。建议选择钢联贸易。", "reasoning": "数据已汇总，以文字形式回复用户"}
"""


def _extract_json(text: str) -> dict:
    """Robust JSON extraction from LLM output.

    Handles: markdown fences, text before/after JSON, trailing commas,
    and nested objects with balanced braces.
    """
    cleaned = text.strip()
    cleaned = re.sub(r'^```(?:json)?\s*\n?', '', cleaned)
    cleaned = re.sub(r'\n?```\s*$', '', cleaned)
    cleaned = cleaned.strip()

    # Attempt 1: direct parse
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        pass

    # Attempt 2: find JSON object with balanced braces
    start = cleaned.find('{')
    if start == -1:
        return _generic_fallback(text)

    depth = 0
    end = -1
    for i in range(start, len(cleaned)):
        if cleaned[i] == '{':
            depth += 1
        elif cleaned[i] == '}':
            depth -= 1
            if depth == 0:
                end = i + 1
                break

    if end > start:
        try:
            return json.loads(cleaned[start:end])
        except json.JSONDecodeError:
            pass

    # Attempt 3: fix common JSON issues (trailing commas, etc.)
    try:
        candidate = cleaned[start:end] if end > start else cleaned[start:]
        candidate = re.sub(r',\s*}', '}', candidate)
        candidate = re.sub(r',\s*]', ']', candidate)
        return json.loads(candidate)
    except json.JSONDecodeError:
        pass

    return _generic_fallback(text)


def _generic_fallback(text: str) -> dict:
    """Generic fallback — extracts intent from LLM prose output.

    Uses Chinese keyword detection first (matching the LLM's Chinese prompt),
    then falls back to English JSON-pattern detection. If nothing works,
    gracefully ends with formatter_text.
    """
    raw = text[:500]

    # ---- Phase 1: Chinese keyword intent detection ----
    tool_keywords = ["调用", "查", "获取", "加载", "查询", "执行工具", "调API"]
    card_keywords = ["卡片", "推荐", "展示结果", "生成卡片"]
    popup_keywords = ["弹窗", "收集", "补充信息", "请提供"]
    text_keywords = ["总结", "回复用户", "文字回复", "告知用户"]

    scores: dict[str, int] = {}
    for kw in tool_keywords:
        if kw in raw:
            scores["tools"] = scores.get("tools", 0) + 1
    for kw in card_keywords:
        if kw in raw:
            scores["formatter_card"] = scores.get("formatter_card", 0) + 1
    for kw in popup_keywords:
        if kw in raw:
            scores["formatter_popup"] = scores.get("formatter_popup", 0) + 1
    for kw in text_keywords:
        if kw in raw:
            scores["formatter_text"] = scores.get("formatter_text", 0) + 1

    # Extract tool_name from Chinese patterns like "调用check_inventory" or "调用 get_quote"
    tool_name = ""
    cn_tool = re.search(r'调用\s*([a-zA-Z_]\w*)', raw)
    if cn_tool:
        tool_name = cn_tool.group(1)

    # Extract skill_name if present
    skill_name = ""
    skill_match = re.search(r'skill_name["\s:：]+["\']?([a-zA-Z0-9_-]+)', raw)
    if skill_match:
        skill_name = skill_match.group(1)

    # Extract api_name if present
    api_name = ""
    api_match = re.search(r'api_name["\s:：]+["\']?([a-zA-Z0-9_-]+)', raw)
    if api_match:
        api_name = api_match.group(1)

    # Build tool_args
    tool_args: dict = {}
    if skill_name:
        tool_args["skill_name"] = skill_name
    if api_name:
        tool_args["api_name"] = api_name
    if skill_name and api_name:
        tool_args.setdefault("params", {})

    if scores:
        best = max(scores, key=scores.get)
        if best == "tools":
            return {
                "next": "tools",
                "tool_name": tool_name,
                "tool_args": tool_args,
                "reasoning": "从中文输出推断: 需要调用工具",
                "_parse_error": True,
            }
        if best in ("formatter_card", "formatter_popup"):
            return {
                "next": best,
                "message": raw,
                "card_type": "trade" if best == "formatter_card" else "",
                "popup_fields": [],
                "card_data": {},
                "reasoning": f"从中文输出推断: {best}",
                "_parse_error": True,
            }
        if best == "formatter_text":
            return {"next": "formatter_text", "message": raw, "reasoning": "从中文输出推断: 文字回复", "_parse_error": True}

    # ---- Phase 2: English JSON-pattern detection ----
    if re.search(r'"next"\s*:\s*"tools"', raw):
        eng_tool = re.search(r'"tool_name"\s*:\s*"(\w+)"', raw)
        tool_name = eng_tool.group(1) if eng_tool else tool_name

        # Extract tool_args with balanced braces (supports nested objects)
        args_start = raw.find('"tool_args"')
        tool_args = {}
        if args_start != -1:
            brace_start = raw.find('{', args_start)
            if brace_start != -1:
                depth = 0
                brace_end = -1
                for i in range(brace_start, len(raw)):
                    if raw[i] == '{':
                        depth += 1
                    elif raw[i] == '}':
                        depth -= 1
                        if depth == 0:
                            brace_end = i + 1
                            break
                if brace_end > brace_start:
                    try:
                        tool_args = json.loads(raw[brace_start:brace_end])
                    except json.JSONDecodeError:
                        pass

        return {
            "next": "tools",
            "tool_name": tool_name,
            "tool_args": tool_args,
            "reasoning": "从LLM输出中提取的工具调用",
            "_parse_error": True,
        }

    # Detect formatter intent from English patterns
    for fmt in ("formatter_text", "formatter_popup", "formatter_card"):
        if fmt in raw:
            return {"next": fmt, "message": raw, "reasoning": "从LLM输出中提取的终止指令", "_parse_error": True}

    # ---- Last resort ----
    return {"next": "formatter_text", "message": raw, "reasoning": "无法解析JSON，作为文本输出", "_parse_error": True}


def create_supervisor_node(get_summaries):
    """Create the Supervisor node — the sole reasoning brain.

    Supervisor receives available skill summaries and the full conversation
    history. It handles everything: completeness checking, skill selection,
    API orchestration, and final output routing.

    The loop: Supervisor → ToolNode → Supervisor (repeat until done).
    """
    llm = get_llm(temperature=0.0, response_format={"type": "json_object"})

    def supervisor_node(state: AgentState) -> Command:
        summaries = get_summaries()
        iteration = state.get("iteration_count", 0) + 1

        # ---- Build system prompt with dynamic context ----
        context_parts = [SUPERVISOR_SYSTEM_PROMPT]

        # Inject available skills
        context_parts.append(f"\n## 当前可用技能\n{summaries}")

        # Iteration counter (informational, encourages progress)
        context_parts.append(f"\n## 循环计数: {iteration}/{MAX_ITERATIONS}")
        if iteration >= MAX_ITERATIONS:
            context_parts.append("⚠️ 已达到最大循环次数。本轮必须路由到 formatter 结束循环，不得再选择 tools。")

        prompt = "\n".join(context_parts)

        # ---- Build message list — filter supervisor's own prose messages ----
        all_msgs = list(state["messages"])
        filtered_msgs = [
            m for m in all_msgs
            if not (isinstance(m, AIMessage) and getattr(m, 'name', None) == 'supervisor')
        ]

        # Inject a concise status summary as SystemMessage (not AIMessage)
        # so the LLM knows what's been done without mimicking prose
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

        # ---- LLM call + JSON extraction ----
        response = llm.invoke(messages)
        decision = _extract_json(response.content)

        # ---- Retry once on parse failure with clearer feedback ----
        if decision.get("_parse_error"):
            retry_prompt = (
                prompt
                + "\n\n## ⚠️ 上一轮输出无法解析为合法JSON\n"
                + f"你的上轮输出: {response.content[:300]}\n\n"
                + "请严格按照格式要求，只输出一行JSON对象。不要用```json```包裹。不要输出推理文字。"
            )
            retry_messages = [SystemMessage(content=retry_prompt)] + recent_msgs
            retry_response = llm.invoke(retry_messages)
            decision = _extract_json(retry_response.content)
            if decision.get("_parse_error"):
                decision = {
                    "next": "formatter_text",
                    "message": "抱歉，处理过程中遇到问题，请重新描述您的需求。",
                    "reasoning": "两次JSON解析均失败，强制终止",
                }

        # ---- Safety: force termination at max iterations ----
        goto = decision.get("next", "formatter_text")
        if iteration >= MAX_ITERATIONS and goto == "tools":
            goto = "formatter_text"
            if not decision.get("message"):
                decision["message"] = "已达到最大处理步骤，以下是根据当前数据的结果汇总。"

        # ---- Build state update ----
        update = {
            "supervisor_decision": decision,
            "iteration_count": iteration,
            "messages": [
                AIMessage(
                    content=json.dumps(decision, ensure_ascii=False),
                    name="supervisor",
                )
            ],
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
