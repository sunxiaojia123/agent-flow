"""Supervisor node — centralized decision controller with structured output routing."""

import json
import re
from langchain_core.messages import SystemMessage, AIMessage
from langgraph.types import Command
from app.graph.state import AgentState
from app.services.llm import get_llm

SUPERVISOR_PROMPT = """你是交易主管(Supervisor)。你必须严格根据状态机规则决定下一步操作。

## 核心规则（必须遵守）

**规则1: 先画像，后技能**
第一轮必须: get_user_context → 第二轮: load_skill_detail

**规则2: 加载技能后必须调用API**
load_skill_detail 只返回"如何调用API的说明文档"，不是真实数据。加载完技能后，必须立即 call_api 获取真实库存/报价数据。严禁在加载技能后直接跳到 formatter。

**规则3: 从用户输入中提取API参数**
用户已经提供了品类、数量、地区等信息。调用 call_api 时直接从用户消息中提取参数值，不需要额外询问。例如用户说"买500吨螺纹钢，上海"，params 就是 {"product_category": "螺纹钢", "quantity": 500}。

**规则4: 标准调用顺序**
对每个供应商: check_inventory(确认库存) → get_quote(获取报价) → check_logistics(查物流)
每个 API 调用都是一次独立的 tools → supervisor 往返。

**规则5: 只有API返回了真实数据，才能到 formatter**
formatter_text: API数据不足以生成卡片时，用文字汇总
formatter_card: 至少拿到 check_inventory + get_quote 两个API结果后，生成推荐卡片
formatter_popup: 用户确实没提供品类/数量/地区时使用

**规则6: 可以比较多个供应商，但不要超过2个**
加载1-2个匹配供应商的 skill，分别调API获取数据后比较推荐。如果两个供应商数据已足够对比，直接生成卡片，不要加载第三个。

## 完整流程示例

用户: "在上海买500吨螺纹钢"

第1轮 supervisor 输出:
{"next": "tools", "tool_name": "get_user_context", "tool_args": {}, "reasoning": "先获取用户画像和采购偏好"}

第2轮(收到user-profile后) supervisor 输出:
{"next": "tools", "tool_name": "load_skill_detail", "tool_args": {"skill_name": "ganglian-supplier"}, "reasoning": "用户在上海，钢联贸易是上海本地供应商且主营螺纹钢，优先加载"}

第3轮(收到skill详情后) supervisor 输出:
{"next": "tools", "tool_name": "call_api", "tool_args": {"skill_name": "ganglian-supplier", "api_name": "check_inventory", "params": {"product_category": "螺纹钢"}}, "reasoning": "skill已加载，立即调用check_inventory查询螺纹钢库存"}

第4轮(收到库存数据后) supervisor 输出:
{"next": "tools", "tool_name": "call_api", "tool_args": {"skill_name": "ganglian-supplier", "api_name": "get_quote", "params": {"product_category": "螺纹钢", "quantity": 500}}, "reasoning": "库存充足，调用get_quote获取500吨报价"}

第5轮(收到报价后) supervisor 输出:
{"next": "tools", "tool_name": "call_api", "tool_args": {"skill_name": "ganglian-supplier", "api_name": "check_logistics", "params": {"destination": "上海", "quantity": 500}}, "reasoning": "获取配送到上海的物流方案"}

第6轮(收到物流数据后) supervisor 输出:
{"next": "formatter_card", "card_type": "trade", "card_data": {"supplier": "钢联贸易", "product": "螺纹钢 HRB400", ...}, "reasoning": "库存/报价/物流全部获取完毕，生成推荐卡片"}

## 输出格式（严格遵守）
你必须只输出一行JSON。不要输出任何解释文字、不要输出Markdown代码块、不要输出推理过程。只输出:
{"next": "<tools|formatter_text|formatter_popup|formatter_card>", "tool_name": "<工具名>", "tool_args": {...}, "message": "...", "popup_fields": [...], "card_type": "...", "card_data": {...}, "reasoning": "..."}
"""


def _extract_json(text: str, state: dict | None = None) -> dict:
    """Extract JSON from LLM response, handling text before/after and nested objects."""
    # Remove markdown code fences if present
    cleaned = re.sub(r'```(?:json)?\s*', '', text)
    cleaned = re.sub(r'```', '', cleaned)

    # Find JSON object with balanced braces
    start = cleaned.find('{')
    if start == -1:
        return _fallback_decision(text, state)

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

    return _fallback_decision(text, state)


def _fallback_decision(text: str, state: dict | None = None) -> dict:
    """When LLM fails to output JSON, try to infer intent from raw text."""
    # Build context for skill name / user input extraction
    context = ""
    if state:
        msgs = state.get("messages", [])
        for m in reversed(msgs):
            if hasattr(m, "content"):
                ctx = str(m.content)
                context = ctx + " " + context
                # Collect all tool responses and user input (not just the last)
                if len(context) > 3000:  # Cap it
                    break

    # Search for API name in the raw LLM text ONLY (not in context)
    # This avoids matching check_inventory from previous tool results
    api_match = re.search(r'(check_inventory|get_quote|check_logistics|get_profile|get_history)', text)

    # Extract skill name from the full context (history messages + raw text)
    skill_match = re.search(r'(ganglian-supplier|shagang-supplier|huadong-supplier|nanjing-supplier|xingcheng-supplier)', context + " " + text)

    if api_match:
        api_name = api_match.group(1)
        skill = skill_match.group(1) if skill_match else "ganglian-supplier"

        params = {}
        qty_match = re.search(r'(\d+)\s*吨', context)
        if qty_match and api_name in ("get_quote", "check_logistics"):
            params["quantity"] = int(qty_match.group(1))

        product_match = re.search(r'(螺纹钢|线材|圆钢|热轧卷板|冷轧卷板|中厚板|H型钢|工字钢|槽钢|角钢|不锈钢板|镀锌板)', context)
        if product_match:
            params["product_category"] = product_match.group(1)

        dest_match = re.search(r'(?:配送|目的地|到)\s*[：:]?\s*(上海|北京|杭州|南京|广州|深圳|武汉|成都)', context)
        if dest_match and api_name == "check_logistics":
            params["destination"] = dest_match.group(1)

        return {
            "next": "tools", "tool_name": "call_api",
            "tool_args": {"skill_name": skill, "api_name": api_name, "params": params},
            "reasoning": f"从文本推断: 调用 {api_name}",
        }

    # Pattern: LLM wants to load a skill
    if skill_match:
        return {
            "next": "tools", "tool_name": "load_skill_detail",
            "tool_args": {"skill_name": skill_match.group(1)},
            "reasoning": f"从文本推断: 加载 {skill_match.group(1)}",
        }

    # Pattern: LLM mentions user context
    if re.search(r'get_user_context|用户画像|用户信息|user.profile', text):
        return {
            "next": "tools", "tool_name": "get_user_context", "tool_args": {},
            "reasoning": "从文本推断: 获取用户画像",
        }

    # Give up — format as text
    return {"next": "formatter_text", "reasoning": "No JSON found", "message": text[:500]}


def create_supervisor_node(get_summaries):
    llm = get_llm(temperature=0.0)

    def supervisor_node(state: AgentState) -> Command:
        summaries = get_summaries()

        prompt = (
            SUPERVISOR_PROMPT
            + f"\n\n## 当前可用技能\n{summaries}\n\n"
            + "## 当前状态\n"
            + "请根据上文的工具执行结果做决策。\n\n"
            + "【重要】如果上一个工具是 load_skill_detail 返回了API列表，你必须立即输出调用 call_api 的JSON。\n"
            + "【重要】如果上一个工具是 call_api 返回了数据，根据规则4决定下一步：继续调API还是到formatter。\n"
            + "【重要】严禁输出任何非JSON内容。只输出一行JSON。不要用```json```包裹。"
        )

        # Limit context to last 20 messages to avoid overflow
        all_msgs = list(state["messages"])
        recent_msgs = all_msgs[-20:] if len(all_msgs) > 20 else all_msgs
        messages = [SystemMessage(content=prompt)] + recent_msgs

        response = llm.invoke(messages)
        decision = _extract_json(response.content, state)

        # Retry once if JSON extraction failed
        if decision.get("reasoning") in ("No JSON found", "JSON parse failed"):
            print(f"[Supervisor raw response]: {response.content[:300]}")
            retry_prompt = (
                prompt
                + "\n\n## 你上次的回复不是JSON格式，请严格按照JSON格式重新输出\n"
                + "你的上次回复: " + response.content[:200] + "\n\n"
                + "现在请只输出一个JSON对象:"
            )
            retry_messages = [SystemMessage(content=retry_prompt)] + recent_msgs
            retry_response = llm.invoke(retry_messages)
            decision = _extract_json(retry_response.content, state)
            if decision.get("reasoning") in ("No JSON found", "JSON parse failed"):
                print(f"[Supervisor retry raw response]: {retry_response.content[:300]}")

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
