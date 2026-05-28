"""Supervisor node — centralized decision controller with structured output routing."""

import json
import re
from langchain_core.messages import SystemMessage, AIMessage
from langgraph.types import Command
from app.graph.state import AgentState
from app.services.llm import get_llm

SUPERVISOR_PROMPT = """你是交易主管(Supervisor)。根据 Planner 的计划和历史执行结果，决定下一步操作。

## 路由选项

### tools — 需要执行工具获取信息
- load_skill_detail: 加载供应商技能详情 (参数: skill_name)
- get_api_schema: 获取 API 参数结构 (参数: skill_name, api_name)
- call_api: 执行 API 调用 (参数: skill_name, api_name, params)
- get_user_context: 获取用户画像和历史采购

### formatter_text — 信息足够，直接文字回答
当用户可以简单回答、不需要卡片展示时使用

### formatter_popup — 缺少关键参数，需要弹窗收集
当用户没有提供: 产品品类、数量、地区等必要信息时使用

### formatter_card — 结果完整，生成卡片展示
当已获取供应商信息、报价、库存等数据，可以给用户推荐时使用

## 决策规则
1. **渐进式加载** — 不要一次性加载所有技能，先加载最匹配的
2. **按需获取 schema** — 调用 API 前先 get_api_schema 了解参数
3. **同一供应商可多次调用** — 先库存→再报价→后物流
4. **可比较多个供应商** — 加载 2-3 个匹配的供应商，比较后推荐
5. **信息不足果断 ask_user** — 不要猜测品类和数量
6. **用户画像优先** — 先 get_user_context 获取偏好
7. **参考 Plan 但灵活调整** — 根据实际返回结果决定

## 输出格式
只输出 JSON，不要任何其他文字:
{"next": "tools或formatter_text或formatter_popup或formatter_card", "tool_name": "...", "tool_args": {...}, "message": "...", "popup_fields": [...], "card_type": "...", "card_data": {...}, "reasoning": "..."}
"""


def _extract_json(text: str) -> dict:
    """Extract JSON from LLM response, handling text before/after and nested objects."""
    # Remove markdown code fences if present
    text = re.sub(r'```(?:json)?\s*', '', text)
    text = re.sub(r'```', '', text)

    # Find JSON object with balanced braces
    start = text.find('{')
    if start == -1:
        return {"next": "formatter_text", "reasoning": "No JSON found", "message": text[:500]}

    depth = 0
    end = -1
    for i in range(start, len(text)):
        if text[i] == '{':
            depth += 1
        elif text[i] == '}':
            depth -= 1
            if depth == 0:
                end = i + 1
                break

    if end > start:
        try:
            return json.loads(text[start:end])
        except json.JSONDecodeError:
            pass

    return {"next": "formatter_text", "reasoning": "JSON parse failed", "message": text[:500]}


def create_supervisor_node(get_summaries):
    llm = get_llm(temperature=0.0)

    def supervisor_node(state: AgentState) -> Command:
        summaries = get_summaries()

        prompt = SUPERVISOR_PROMPT + f"\n\n## 当前可用技能\n{summaries}\n\n## 已加载的技能和工具调用历史\n请根据上文的工具执行结果做决策。\n\n当前你必须只输出一个JSON对象，不要输出任何解释文字。"

        # Limit context to last 20 messages to avoid overflow
        all_msgs = list(state["messages"])
        recent_msgs = all_msgs[-20:] if len(all_msgs) > 20 else all_msgs
        messages = [SystemMessage(content=prompt)] + recent_msgs

        response = llm.invoke(messages)
        decision = _extract_json(response.content)
        if decision.get("reasoning", "") in ("No JSON found", "JSON parse failed"):
            # Log the raw response for debugging
            print(f"[Supervisor raw response]: {response.content[:300]}")

        goto = decision.get("next", "formatter_text")

        # Build update
        update = {
            "supervisor_decision": decision,
            "messages": [AIMessage(
                content=f"[Supervisor] → {goto}: {decision.get('reasoning', '')}",
                name="supervisor"
            )],
        }

        # Carry formatter data in state if ending
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
