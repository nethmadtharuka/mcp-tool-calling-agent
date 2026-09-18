"""LLM provider abstraction.

Isolated here so swapping or adding providers later doesn't touch the
graph or API layers.
"""

from typing import Protocol

from langchain_core.messages import AIMessage, BaseMessage

from app.core.config import Settings


class ChatModel(Protocol):
    def invoke(self, messages: list[BaseMessage]) -> AIMessage: ...

    # A real ChatOpenAI already has bind_tools built in. MockChatModel
    # needs one too, purely so LLM_PROVIDER=mock doesn't crash once
    # nodes.py starts calling llm.bind_tools(...) unconditionally.
    def bind_tools(self, tools: list) -> "ChatModel": ...


class MockChatModel:
    """Deterministic stand-in used when LLM_PROVIDER=mock, so the app runs
    end-to-end without any API key."""

#why we use mock chat model with also the OpenAI API,
#because when doing tests each and every time it costs
#there fore we use mock agent for testing
    def invoke(self, messages: list[BaseMessage]) -> AIMessage:
        last_message = messages[-1].content if messages else ""
        return AIMessage(content=f"[mock response] You said: {last_message}")

    def bind_tools(self, tools: list) -> "MockChatModel":
        # The mock never decides to call a tool - it just ignores them.
        return self


def get_llm(settings: Settings) -> ChatModel:
    if settings.mock_mode:
        return MockChatModel()

    if settings.llm_provider == "openai":
        from langchain_openai import ChatOpenAI

        return ChatOpenAI(model=settings.llm_model, api_key=settings.llm_api_key)

    raise ValueError(f"Unsupported LLM_PROVIDER: {settings.llm_provider}")
