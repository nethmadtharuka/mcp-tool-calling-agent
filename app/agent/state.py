"""State definition for the LangGraph workflow."""

from typing import TypedDict


class AgentState(TypedDict):
    message: str
    response: str

#The information currently being carried through the agent workflow.
#right now we only have the massage and the respoonse only 
# #For example:

# {
#     "message": "Hello",
#     "response": ""
# }

# After the LLM:

# {
#     "message": "Hello",
#     "response": "Hello! How can I help?"
# }


# Why do we need state?

# Because LangGraph is designed for workflows.

# Imagine later:

# START
#  ↓
# Understand request
#  ↓
# Search GitHub
#  ↓
# Analyze issue
#  ↓
# Read source code
#  ↓
# Generate answer
#  ↓
# END

# Each step needs information from previous steps.

# State is how we carry that information.

# Eventually our state could become:

# AgentState
# │
# ├── user_message
# ├── messages
# ├── repository
# ├── issues
# ├── files
# ├── tool_results
# ├── analysis
# └── final_answer

# But not yet.

# For Phase 1:

# message
# response

# is enough.