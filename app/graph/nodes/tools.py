"""ToolNode — dispatches and executes the tool specified by Supervisor."""

import inspect
import json
from langchain_core.messages import ToolMessage
from langgraph.types import Command
from app.graph.state import AgentState
from app.tools.skill_tools import load_skill_detail, get_api_schema
from app.tools.api_tools import call_api
from app.tools.user_tools import get_user_context


# Mapping from tool_name to function + expected params
TOOL_TABLE = {
    "load_skill_detail": load_skill_detail,
    "get_api_schema": get_api_schema,
    "call_api": call_api,
    "get_user_context": get_user_context,
}


def _filter_kwargs(func, kwargs: dict) -> dict:
    """Only keep kwargs that the function actually accepts."""
    sig = inspect.signature(func)
    valid = set(sig.parameters.keys())
    return {k: v for k, v in kwargs.items() if k in valid}


def _friendly_tool_name(tool_name: str) -> str:
    names = {
        "get_user_context": "获取用户画像",
        "load_skill_detail": "加载技能详情",
        "call_api": "调用API",
        "get_api_schema": "获取API Schema",
    }
    return names.get(tool_name, tool_name)


def create_tool_node():
    def tool_node(state: AgentState) -> Command:
        decision = state.get("supervisor_decision", {})
        tool_name = decision.get("tool_name", "")
        tool_args = decision.get("tool_args", {})

        func = TOOL_TABLE.get(tool_name)
        if func is None:
            result = {"error": f"Unknown tool: {tool_name}"}
        else:
            try:
                filtered = _filter_kwargs(func, tool_args)
                result = func(**filtered)
            except Exception as e:
                result = {"error": f"Tool execution failed: {str(e)}"}

        result_str = json.dumps(result, ensure_ascii=False, indent=2)

        tool_call_id = decision.get("tool_call_id", "")

        return Command(
            goto="supervisor",
            update={
                "messages": [ToolMessage(
                    content=f"[ToolNode: {tool_name} 返回]\n{result_str}",
                    name=tool_name,
                    tool_call_id=tool_call_id,
                )]
            }
        )

    return tool_node
