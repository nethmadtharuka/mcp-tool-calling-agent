"""LangGraph node functions."""

import logging

from langchain_core.messages import ToolMessage

from app.agent.llm import get_llm
from app.agent.mcp_tools import get_mcp_tools
from app.agent.state import AgentState
from app.agent.tools import AVAILABLE_TOOLS
from app.core.config import get_settings

logger = logging.getLogger(__name__)


async def _get_all_tools() -> list:
    """Local Phase 2 tool(s) + whatever GitHub MCP tools are discovered.

    Both kinds end up as the same LangChain tool interface, so nodes
    below don't need to know or care which is which.
    """
    settings = get_settings()
    mcp_tools = await get_mcp_tools(settings)
    return AVAILABLE_TOOLS + mcp_tools


async def agent_node(state: AgentState) -> AgentState:
    """Send the conversation so far to the LLM.

    bind_tools() attaches the tool schemas to the request, so the LLM can
    either answer directly (AIMessage with no tool_calls) or ask to run a
    tool (AIMessage with tool_calls=[{"name": ..., "args": ..., "id": ...}]).
    Deciding which one to do is entirely up to the LLM - we never force it.
    """
    tools = await _get_all_tools()
    llm = get_llm(get_settings()).bind_tools(tools)

    logger.info("Calling LLM with %d message(s) in history", len(state["messages"]))
    ai_message = await llm.ainvoke(state["messages"])

    if ai_message.tool_calls:
        names = [call["name"] for call in ai_message.tool_calls]
        logger.info("LLM requested tool call(s): %s", names)
    else:
        logger.info("LLM answered directly, no tool call requested")

    return {"messages": [ai_message]}


async def tool_node(state: AgentState) -> AgentState:
    """Execute every tool call requested by the last AIMessage.

    ainvoke() works for both the local Phase 2 tool and GitHub MCP tools -
    LangChain runs a sync tool in a thread automatically, and calls an MCP
    tool's real async network path directly.

    Each result is wrapped in a ToolMessage tagged with the matching
    tool_call_id, so the LLM can line the result back up with its request
    on the next turn.
    """
    tools_by_name = {t.name: t for t in await _get_all_tools()}
    last_message = state["messages"][-1]
    results: list[ToolMessage] = []

    for call in last_message.tool_calls:
        name = call["name"]
        args = call["args"]
        call_id = call["id"]
        logger.info("Executing tool '%s' with args %s", name, args)

        tool_fn = tools_by_name.get(name)
        if tool_fn is None:
            content = f"Error: unknown tool '{name}'"
        else:
            try:
                content = str(await tool_fn.ainvoke(args))
            except Exception as exc:  # tool crashed or got bad arguments
                content = f"Error executing '{name}': {exc}"

        logger.info("Tool '%s' result: %s", name, content)
        results.append(ToolMessage(content=content, tool_call_id=call_id))

    return {"messages": results}
