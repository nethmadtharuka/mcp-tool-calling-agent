"""The one local tool the agent can call in Phase 2.

@tool turns a plain Python function into a LangChain tool: it reads the
function's name, type hints, and docstring to build the JSON schema the
LLM is shown, so the LLM knows the tool exists and how to call it.
"""

from langchain_core.tools import tool


@tool
def get_project_info() -> str:
    """Return basic information about this project: its name and phase."""
    return (
        "This project is the Production-Oriented AI Engineering Agent, "
        "currently in Phase 2 (tool calling fundamentals)."
    )


# Single source of truth for "what tools exist" - both the agent node
# (to bind them to the LLM) and the tool node (to execute them) import
# this instead of each keeping their own list.
AVAILABLE_TOOLS = [get_project_info]
