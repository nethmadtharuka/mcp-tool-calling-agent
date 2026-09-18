"""State definition for the LangGraph workflow."""

from typing import Annotated, TypedDict

from langchain_core.messages import BaseMessage
from langgraph.graph.message import add_messages


class AgentState(TypedDict):
    # add_messages is a LangGraph reducer: a node only returns the NEW
    # message(s) it produced, and LangGraph appends them onto this list
    # for us. Without it we'd have to manually concatenate history in
    # every node.
    #
    # Over one tool-calling request this list grows like:
    #   [HumanMessage]                                   after the user asks
    #   [HumanMessage, AIMessage(tool_calls=[...])]       agent decides to call a tool
    #   [..., ToolMessage(result)]                        tool node runs the function
    #   [..., AIMessage(final answer)]                    agent reads the result, answers
    messages: Annotated[list[BaseMessage], add_messages]
