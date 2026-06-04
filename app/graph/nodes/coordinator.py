"""Coordinator node — entry point that classifies intent and routes."""

from langchain_core.messages import SystemMessage, AIMessage, ToolMessage
from langgraph.types import Command
from app.graph.state import AgentState
from app.services.llm import get_llm

COORDINATOR_PROMPT = """你是交易助手协调员。判断用户意图，只回复一个英文标记:

## 判断规则
- 如果是简单问候(如"你好"、"早上好")、感谢、告别 → 直接回复用户，并在回复末尾加上 [DIRECT]
- 如果是知识问答(如"Q235和Q345的区别"、"什么是螺纹钢") → 直接回答问题，并在回复末尾加上 [DIRECT]
- 如果是交易相关需求(采购钢材、询价、查库存、物流查询、供应商对比等) → 只回复 handoff_to_supervisor，不要做其他解释
- 如果用户追问某个供应商的详情 → 只回复 handoff_to_supervisor
- 如果用户说"选这家"、"就第一家的"等选商意图 → 只回复 handoff_to_supervisor

## 重要
对于交易需求，你只需要回复 "handoff_to_supervisor" 这几个字，让 Supervisor 来处理。"""


def _visible_messages(all_msgs: list) -> list:
    """Filter messages to only user-visible conversation content.

    Internal execution messages (AIMessage with tool_calls, ToolMessage,
    supervisor status injections) are stripped so the coordinator sees
    a clean conversation and is not distracted into mimicking tool calls.
    """
    visible = []
    for m in all_msgs:
        # Skip tool-execution messages
        if isinstance(m, ToolMessage):
            continue
        if isinstance(m, AIMessage) and getattr(m, "tool_calls", None):
            continue
        # Skip internal system messages (supervisor status, prompts)
        if isinstance(m, SystemMessage):
            content = getattr(m, "content", "")
            if content.startswith("[状态]") or "循环计数" in content:
                continue
        visible.append(m)
    return visible


def create_coordinator_node():
    llm = get_llm()

    def coordinator_node(state: AgentState) -> Command:
        visible = _visible_messages(list(state["messages"]))
        messages = [SystemMessage(content=COORDINATOR_PROMPT)] + visible
        response = llm.invoke(messages)

        if "handoff_to_supervisor" in response.content:
            return Command(goto="supervisor", update={"coordinator_reply": None, "iteration_count": 0})

        # Direct reply (chitchat or knowledge)
        reply = response.content.replace("[DIRECT]", "").strip()
        return Command(
            goto="formatter_text",
            update={
                "coordinator_reply": reply,
                "final_action": "text",
            }
        )

    return coordinator_node
