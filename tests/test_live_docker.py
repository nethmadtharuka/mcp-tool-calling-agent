"""Opt-in: checks the RUNNING production compose stack. Not mocked.

    docker compose up -d --build
    DOCKER_TESTS=1 pytest tests/test_live_docker.py -v

Run against docker-compose.yml alone: with docker-compose.dev.yml the MCP
ports are published on purpose and test_only_agent_is_published fails.
GitHub checks run only when the agent has a GITHUB_PERSONAL_ACCESS_TOKEN.
No paid LLM call is made: the agent request is skipped unless the
container runs LLM_PROVIDER=mock.
"""

import json
import os
import subprocess
import time
import urllib.request

import pytest

from tests.live_common import PROBE, REPO, check_probe, leaked, parse_probe, secret_values

pytestmark = pytest.mark.skipif(os.getenv("DOCKER_TESTS") != "1", reason="set DOCKER_TESTS=1 to run (needs `docker compose up -d`)")

SERVICES = ("agent", "github-mcp", "filesystem-mcp")


def run(*args, input=None, timeout=180):
    return subprocess.run(args, cwd=REPO, input=input, capture_output=True, text=True,
                          encoding="utf-8", errors="replace", timeout=timeout)


def compose(*args, **kw):
    return run("docker", "compose", *args, **kw)


@pytest.fixture(scope="module")
def containers():
    ps = compose("ps", "--format", "json")
    if ps.returncode != 0:
        pytest.fail(f"Prerequisite: Docker must be running ({ps.stderr.strip()[:200]})")
    rows = [json.loads(line) for line in ps.stdout.splitlines() if line.strip()]
    found = {r["Service"]: r["Name"] for r in rows if r["State"] == "running"}
    missing = [s for s in SERVICES if s not in found]
    if missing:
        pytest.fail(f"Prerequisite: `docker compose up -d` (not running: {missing})")
    return found


def inspect(name, fmt):
    return run("docker", "inspect", "-f", fmt, name).stdout.strip()


def test_compose_config_valid():
    for files in (["-f", "docker-compose.yml"], ["-f", "docker-compose.yml", "-f", "docker-compose.dev.yml"]):
        r = compose(*files, "config", "--quiet")  # --quiet: never prints .env values
        assert r.returncode == 0, r.stderr[:500]


def test_services_healthy(containers):
    deadline = time.time() + 90
    while True:
        health = {s: inspect(containers[s], "{{if .State.Health}}{{.State.Health.Status}}{{end}}") for s in SERVICES}
        if health["agent"] == "healthy" and health["filesystem-mcp"] == "healthy" or time.time() > deadline:
            break
        time.sleep(3)
    assert health["agent"] == "healthy"
    assert health["filesystem-mcp"] == "healthy"
    assert health["github-mcp"] == ""  # no healthcheck possible (distroless), just running


def test_only_agent_is_published_on_localhost(containers):
    bindings = {s: json.loads(inspect(containers[s], "{{json .HostConfig.PortBindings}}") or "{}") for s in SERVICES}
    assert bindings["agent"] == {"8000/tcp": [{"HostIp": "127.0.0.1", "HostPort": "8000"}]}
    assert not bindings["github-mcp"], "github-mcp is published (dev override running?)"
    assert not bindings["filesystem-mcp"], "filesystem-mcp is published (dev override running?)"


def test_runtime_hardening(containers):
    users = {"agent": "app", "github-mcp": "65532:65532", "filesystem-mcp": "node"}
    for s in SERVICES:
        c = containers[s]
        assert inspect(c, "{{.Config.User}}") == users[s], s
        assert inspect(c, "{{.HostConfig.ReadonlyRootfs}}") == "true", s
        assert inspect(c, "{{json .HostConfig.CapDrop}}") == '["ALL"]', s
        assert "no-new-privileges:true" in inspect(c, "{{json .HostConfig.SecurityOpt}}"), s
    assert compose("exec", "-T", "agent", "id", "-u").stdout.strip() == "10001"


def test_health_endpoint(containers):
    with urllib.request.urlopen("http://127.0.0.1:8000/health", timeout=10) as r:
        assert json.load(r) == {"status": "ok"}


def test_agent_run_with_mock_llm(containers):
    provider = compose("exec", "-T", "agent", "printenv", "LLM_PROVIDER").stdout.strip() or "mock"
    if provider != "mock":
        pytest.skip(f"LLM_PROVIDER={provider} in the container: skipped to avoid a paid LLM call")
    req = urllib.request.Request("http://127.0.0.1:8000/api/agent/run", method="POST",
                                 data=b'{"message": "live test"}', headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=120) as r:
        assert "live test" in json.load(r)["response"]


@pytest.fixture(scope="module")
def probe(containers):
    r = compose("exec", "-T", "agent", "python", "-", input=PROBE.read_text())
    assert r.returncode == 0, f"probe failed: {r.stderr[-800:]}"
    return parse_probe(r.stdout)


def test_mcp_over_http_from_agent(probe):
    """Real MCP calls from the agent container: discovery, allowlist,
    .env denied, writes blocked, multi-step graph, step limit, a dead
    MCP server handled, and (with a PAT) GitHub read-only."""
    check_probe(probe)
    if not probe["github_enabled"]:
        pytest.skip("GitHub checks need GITHUB_PERSONAL_ACCESS_TOKEN in .env (filesystem checks passed)")


def test_supergateway_reaps_sessions(containers, probe):
    # The probe opened and closed many MCP sessions; none may leave a
    # stdio child behind.
    deadline = time.time() + 30
    while True:
        args = compose("exec", "-T", "filesystem-mcp", "ps", "-o", "args").stdout.splitlines()
        assert any("supergateway" in a for a in args), "couldn't list processes"  # not vacuous
        children = [a for a in args if a.startswith("node /app/dist/index.js")]
        if not children or time.time() > deadline:
            break
        time.sleep(2)
    assert children == [], f"{len(children)} leftover filesystem server process(es)"


def test_no_secrets_in_image_or_logs(containers):
    assert compose("exec", "-T", "agent", "ls", "-A", "/app").stdout.split() == ["app", "requirements.txt"]
    if not secret_values():
        pytest.skip("no secrets in .env to look for")
    image = inspect(containers["agent"], "{{.Image}}")
    assert not leaked(run("docker", "history", "--no-trunc", image).stdout), "secret in image history"
    assert not leaked(inspect(containers["agent"], "{{json .Config.Labels}}")), "secret in labels"
    assert not leaked(compose("logs", "--no-color").stdout), "secret in compose logs"
