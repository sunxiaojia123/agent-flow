"""Graph builder — assembles the LangGraph state machine with Command-based routing."""

from langgraph.graph import StateGraph, START, END
from langgraph.checkpoint.memory import MemorySaver

from app.graph.state import AgentState
from app.graph.nodes.coordinator import create_coordinator_node
from app.graph.nodes.planner import create_planner_node
from app.graph.nodes.supervisor import create_supervisor_node
from app.graph.nodes.tools import create_tool_node
from app.graph.nodes.formatter import (
    create_formatter_text_node,
    create_formatter_popup_node,
    create_formatter_card_node,
)
from app.tools.skill_tools import set_registry as set_skill_registry
from app.tools.api_tools import set_registry as set_api_registry
from app.tools.user_tools import set_registry as set_user_registry


def build_graph(skill_registry=None):
    """Build the LangGraph workflow.

    Graph structure:
    START → coordinator → (planner → supervisor ⇄ tools) → formatter_* → END

    All routing is dynamic via Command(goto=...).
    """
    # Set up tool registry access
    if skill_registry:
        set_skill_registry(skill_registry)
        set_api_registry(skill_registry)
        set_user_registry(skill_registry)

    def get_summaries():
        if skill_registry:
            return skill_registry.summaries
        return ""

    # Create nodes
    coordinator_node = create_coordinator_node()
    planner_node = create_planner_node(get_summaries)
    supervisor_node = create_supervisor_node(get_summaries)
    tool_node = create_tool_node()
    formatter_text_node = create_formatter_text_node()
    formatter_popup_node = create_formatter_popup_node()
    formatter_card_node = create_formatter_card_node()

    # Build graph
    builder = StateGraph(AgentState)

    builder.add_node("coordinator", coordinator_node)
    builder.add_node("planner", planner_node)
    builder.add_node("supervisor", supervisor_node)
    builder.add_node("tools", tool_node)
    builder.add_node("formatter_text", formatter_text_node)
    builder.add_node("formatter_popup", formatter_popup_node)
    builder.add_node("formatter_card", formatter_card_node)

    # Only static edge: START → coordinator
    builder.add_edge(START, "coordinator")

    # All other edges are dynamic via Command(goto=...) from each node
    # coordinator → planner | formatter_text
    # planner → supervisor
    # supervisor → tools | formatter_text | formatter_popup | formatter_card
    # tools → supervisor (loop back)
    # formatter_* → __end__

    checkpointer = MemorySaver()
    return builder.compile(checkpointer=checkpointer)
