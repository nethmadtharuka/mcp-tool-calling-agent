"""The LangGraph workflow.

Phase 1 was a straight line: START -> agent -> END.
Phase 2 adds a loop so the agent can call a tool and read the result
before answering:

    START -> agent -> (tool requested?) -> tool -> agent -> END
                    -> (no)             -> END
"""

from langchain_core.messages import HumanMessage
from langgraph.graph import END, START, StateGraph

from app.agent.nodes import agent_node, tool_node
from app.agent.state import AgentState


def route_after_agent(state: AgentState) -> str:
    """Conditional edge: inspect the last AIMessage to decide where to go next."""
    last_message = state["messages"][-1]
    if last_message.tool_calls:
        return "tool"
    return "end"


def build_graph():
    graph = StateGraph(AgentState)
    graph.add_node("agent", agent_node)
    graph.add_node("tool", tool_node)

    graph.add_edge(START, "agent")
    graph.add_conditional_edges("agent", route_after_agent, {"tool": "tool", "end": END})
    graph.add_edge("tool", "agent")  # after running the tool, go back and let the LLM answer

    return graph.compile()


_compiled_graph = build_graph()


async def run_agent(message: str) -> str:
    # ainvoke, not invoke: agent_node/tool_node now await GitHub MCP calls
    # (stdio/network I/O), so the whole graph runs async.
    result = await _compiled_graph.ainvoke({"messages": [HumanMessage(content=message)]})
    return result["messages"][-1].content
