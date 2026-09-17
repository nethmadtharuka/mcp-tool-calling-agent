import os

os.environ.setdefault("LLM_PROVIDER", "mock")

from fastapi.testclient import TestClient

from app.agent.graph import run_agent
from app.main import app

client = TestClient(app)


def test_agent_run_returns_mock_response():
    response = client.post("/api/agent/run", json={"message": "hello"})
    assert response.status_code == 200
    assert "hello" in response.json()["response"]


def test_agent_run_rejects_empty_message():
    response = client.post("/api/agent/run", json={"message": ""})
    assert response.status_code == 422


def test_agent_run_rejects_missing_field():
    response = client.post("/api/agent/run", json={})
    assert response.status_code == 422


def test_graph_execution_directly():
    result = run_agent("ping")
    assert "ping" in result
