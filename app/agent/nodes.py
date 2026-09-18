"""LangGraph node functions."""

import logging

from langchain_core.messages import ToolMessage

from app.agent.llm import get_llm
from app.agent.state import AgentState
from app.agent.tools import AVAILABLE_TOOLS
from app.core.config import get_settings

logger = logging.getLogger(__name__)

# name -> tool, so the tool node can look up which function to run.
TOOLS_BY_NAME = {t.name: t for t in AVAILABLE_TOOLS}


def agent_node(state: AgentState) -> AgentState:
    """Send the conversation so far to the LLM.

    bind_tools() attaches the tool schemas to the request, so the LLM can
    either answer directly (AIMessage with no tool_calls) or ask to run a
    tool (AIMessage with tool_calls=[{"name": ..., "args": ..., "id": ...}]).
    Deciding which one to do is entirely up to the LLM - we never force it.
    """
    llm = get_llm(get_settings()).bind_tools(AVAILABLE_TOOLS)

    logger.info("Calling LLM with %d message(s) in history", len(state["messages"]))
    ai_message = llm.invoke(state["messages"])

    if ai_message.tool_calls:
        names = [call["name"] for call in ai_message.tool_calls]
        logger.info("LLM requested tool call(s): %s", names)
    else:
        logger.info("LLM answered directly, no tool call requested")

    return {"messages": [ai_message]}


def tool_node(state: AgentState) -> AgentState:
    """Execute every tool call requested by the last AIMessage.

    Each result is wrapped in a ToolMessage tagged with the matching
    tool_call_id, so the LLM can line the result back up with its request
    on the next turn.
    """
    last_message = state["messages"][-1]
    results: list[ToolMessage] = []

    for call in last_message.tool_calls:
        name = call["name"]
        args = call["args"]
        call_id = call["id"]
        logger.info("Executing tool '%s' with args %s", name, args)

        tool_fn = TOOLS_BY_NAME.get(name)
        if tool_fn is None:
            content = f"Error: unknown tool '{name}'"
        else:
            try:
                content = str(tool_fn.invoke(args))
            except Exception as exc:  # tool crashed or got bad arguments
                content = f"Error executing '{name}': {exc}"

        logger.info("Tool '%s' result: %s", name, content)
        results.append(ToolMessage(content=content, tool_call_id=call_id))

    return {"messages": results}
