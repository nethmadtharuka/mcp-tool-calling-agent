"""Shared by the opt-in live tests (test_live_docker.py, test_live_k8s.py).
Not a test module itself."""

import json
from pathlib import Path

from dotenv import dotenv_values

REPO = Path(__file__).resolve().parents[1]
PROBE = Path(__file__).with_name("live_probe.py")


def secret_values() -> list[str]:
    """The real secret values from .env, for "is it leaked?" checks.
    Only ever compared, never printed or put in an assertion message."""
    env = dotenv_values(REPO / ".env")
    return [v for k, v in env.items() if k in ("LLM_API_KEY", "GITHUB_PERSONAL_ACCESS_TOKEN") and v]


def leaked(text: str) -> bool:
    return any(v in text for v in secret_values())


def parse_probe(stdout: str) -> dict:
    return json.loads(stdout.strip().splitlines()[-1])


def check_probe(out: dict) -> None:
    """Assertions on tests/live_probe.py's output, same for compose and k8s."""
    assert out["fs_read_tools_present"], "filesystem read tools not discovered"
    assert out["fs_write_tools_offered"] == [], "allowlist let write tools through"
    assert out["readme_readable"], "README.md not readable through filesystem MCP"
    not_denied = [p for p, ok in out["secret_paths_denied"].items() if not ok]
    assert not not_denied, f"readable through filesystem MCP: {not_denied}"
    assert out["env_in_listing"] is False, ".env/.git/.venv visible in directory listing"
    assert out["write_file_erofs"] and out["edit_file_erofs"], "filesystem is writable"

    assert out["graph_answered"], "graph didn't finish"
    assert out["graph_write_tools_bound"] == [], "write tools were bound to the LLM"
    assert out["graph_list_dirs_ok"] and out["graph_read_readme_ok"], "multi-step filesystem calls failed"
    assert out["graph_read_env_denied"], ".env readable through the agent"
    assert out["graph_write_refused"], "write_file wasn't refused as unknown"

    assert out["max_tool_steps"] == 8
    assert out["step_limit_stopped"] and out["step_limit_turns"] == 9, "step limit not enforced"

    assert out["fs_down_handled"] is True, f"dead MCP server not handled: {out['fs_down_handled']}"
    assert out["fs_down_not_cached"], "partial tool list was cached"

    if out["github_enabled"]:
        assert out["github_write_tools_readonly_false"] == [], "X-MCP-Readonly: false exposed write tools"
        assert out["github_tools_readonly_false"] > 0
        assert out["graph_github_search_ok"], "GitHub tool call through the agent failed"
