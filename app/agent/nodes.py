"""LangGraph node functions."""

from langchain_core.messages import HumanMessage

from app.agent.llm import get_llm
from app.agent.state import AgentState
from app.core.config import get_settings


def agent_node(state: AgentState) -> AgentState:
    llm = get_llm(get_settings())
    result = llm.invoke([HumanMessage(content=state["message"])])
    return {"message": state["message"], "response": result.content}
