"""The LangGraph workflow: START -> agent -> END."""

from langgraph.graph import END, START, StateGraph

from app.agent.nodes import agent_node
from app.agent.state import AgentState


def build_graph():
    graph = StateGraph(AgentState)
    graph.add_node("agent", agent_node)
    graph.add_edge(START, "agent")
    graph.add_edge("agent", END)
    return graph.compile()


_compiled_graph = build_graph()


def run_agent(message: str) -> str:
    result = _compiled_graph.invoke({"message": message, "response": ""})
    return result["response"]
