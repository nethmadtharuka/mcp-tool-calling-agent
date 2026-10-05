"""The LangGraph workflow.

Phase 1 was a straight line: START -> agent -> END.
Phase 2 adds a loop so the agent can call a tool and read the result
before answering:

    START -> agent -> (tool requested?) -> tool -> agent -> END
                    -> (no)             -> END

Phase 5: the tool -> agent edge already loops, so the LLM can chain
several tool calls (across any MCP server) before answering. The only
addition is a hard cap so a model that never stops calling tools can't
loop forever.
"""

import logging

from langchain_core.messages import HumanMessage
from langgraph.errors import GraphRecursionError
from langgraph.graph import END, START, StateGraph

from app.agent.nodes import agent_node, tool_node
from app.agent.state import AgentState

# Max agent -> tool round trips per request.
MAX_TOOL_STEPS = 8
# LangGraph counts every node run as one step: each round trip is agent +
# tool (2), plus the final agent turn that answers (1).
_RECURSION_LIMIT = 2 * MAX_TOOL_STEPS + 1


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


logger = logging.getLogger(__name__)

_compiled_graph = build_graph()


def _as_text(content: str | list) -> str:
    # OpenAI/mock return content as a plain string. Gemini returns a list
    # of content blocks (e.g. [{"type": "text", "text": "..."}]) instead.
    if isinstance(content, str):
        return content
    return "".join(
        block.get("text", "") if isinstance(block, dict) else str(block)
        for block in content
    )


async def run_agent(message: str) -> str:
    # ainvoke, not invoke: agent_node/tool_node now await GitHub MCP calls
    # (stdio/network I/O), so the whole graph runs async.
    try:
        result = await _compiled_graph.ainvoke(
            {"messages": [HumanMessage(content=message)]},
            config={"recursion_limit": _RECURSION_LIMIT},
        )
    except GraphRecursionError:
        logger.warning("Stopped after %d tool steps without a final answer", MAX_TOOL_STEPS)
        return f"Stopped: reached the limit of {MAX_TOOL_STEPS} tool steps without a final answer."
    return _as_text(result["messages"][-1].content)
