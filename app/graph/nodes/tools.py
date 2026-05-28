"""ToolNode — dispatches and executes the tool specified by Supervisor."""

import json
from langchain_core.messages import HumanMessage
from langgraph.types import Command
from app.graph.state import AgentState
from app.tools.skill_tools import load_skill_detail, get_api_schema
from app.tools.api_tools import call_api
from app.tools.user_tools import get_user_context


def create_tool_node():
    def tool_node(state: AgentState) -> Command:
        decision = state.get("supervisor_decision", {})
        tool_name = decision.get("tool_name", "")
        tool_args = decision.get("tool_args", {})

        # Dispatch to tool function
        try:
            if tool_name == "load_skill_detail":
                result = load_skill_detail(**tool_args)
            elif tool_name == "get_api_schema":
                result = get_api_schema(**tool_args)
            elif tool_name == "call_api":
                result = call_api(**tool_args)
            elif tool_name == "get_user_context":
                result = get_user_context()
            else:
                result = {"error": f"Unknown tool: {tool_name}"}
        except Exception as e:
            result = {"error": f"Tool execution failed: {str(e)}"}

        result_str = json.dumps(result, ensure_ascii=False, indent=2)

        return Command(
            goto="supervisor",
            update={
                "messages": [HumanMessage(
                    content=f"[ToolNode: {tool_name} 返回]\n{result_str}",
                    name=tool_name,
                )]
            }
        )

    return tool_node
