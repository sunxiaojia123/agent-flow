"""Planner node — creates structured execution plan for trading requests."""

import json
import re
from langchain_core.messages import SystemMessage, HumanMessage
from langgraph.types import Command
from app.graph.state import AgentState
from app.services.llm import get_llm


def _extract_json(text: str) -> dict:
    match = re.search(r'\{.*\}', text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(0))
        except json.JSONDecodeError:
            pass
    return {"thought": text[:200], "steps": []}


def create_planner_node(get_summaries):
    llm = get_llm()

    def planner_node(state: AgentState) -> Command:
        summaries = get_summaries()

        system_prompt = f"""你是交易规划员。分析用户需求，制定结构化的执行计划。

## 可用技能
{summaries}

## 输出 (只输出JSON)
{{"thought": "分析描述", "steps": [{{"skill": "技能名", "action": "动作", "description": "说明"}}]}}

## 规划指南
- 先加载 user-profile 获取用户偏好
- 根据用户需求的品类和地区，选择匹配的供应商
- 优先匹配主营品类包含用户需求品类的供应商
"""

        messages = [
            SystemMessage(content=system_prompt),
            HumanMessage(content=f"用户需求: {state['messages'][-1].content if state['messages'] else '无'}"),
        ]

        response = llm.invoke(messages)
        plan = _extract_json(response.content)

        return Command(
            goto="supervisor",
            update={
                "plan": plan,
                "messages": [HumanMessage(
                    content=f"[Planner] {plan.get('thought', '')}\n计划步骤: {plan.get('steps', [])}",
                    name="planner"
                )]
            }
        )

    return planner_node
