"""Opt-in: checks the RUNNING Kubernetes deployment (README "Phase 8"). Not mocked.

    K8S_TESTS=1 pytest tests/test_live_k8s.py -v                    # kind-mcp-agent
    K8S_TESTS=1 K8S_CONTEXT=docker-desktop pytest tests/test_live_k8s.py -v

Always uses an explicit --context. The NetworkPolicy matrix runs only
where k8s/network-policies.yaml is applied, and must run on a cluster
that enforces it (kind + Calico): on docker-desktop it is skipped as
"not enforced", never passed. It creates three temporary pods (deleted
afterwards); every "blocked" result is paired with a control showing the
target is reachable from a pod without policies.
"""

import hashlib
import json
import os
import re
import subprocess
import time
import urllib.request

import pytest

from tests.live_common import PROBE, REPO, check_probe, parse_probe, secret_values

pytestmark = pytest.mark.skipif(os.getenv("K8S_TESTS") != "1", reason="set K8S_TESTS=1 to run (needs the Phase 8 deployment)")

CTX = os.getenv("K8S_CONTEXT", "kind-mcp-agent")
NS = "mcp-agent"
APPS = ("agent", "github-mcp", "filesystem-mcp")


def kubectl(*args, input=None, timeout=120):
    return subprocess.run(["kubectl", "--context", CTX, *args], cwd=REPO, input=input, capture_output=True,
                          text=True, encoding="utf-8", errors="replace", timeout=timeout)


def jget(*args):
    r = kubectl(*args, "-o", "json")
    assert r.returncode == 0, r.stderr[:300]
    return json.loads(r.stdout)


@pytest.fixture(scope="module")
def deployed():
    r = kubectl("-n", NS, "get", "deploy", "-o", "json", timeout=30)
    if r.returncode != 0:
        pytest.fail(f"Prerequisite: context {CTX!r} reachable with namespace {NS} ({r.stderr.strip()[:200]})")
    ready = {d["metadata"]["name"]: d["status"].get("availableReplicas", 0) for d in json.loads(r.stdout)["items"]}
    missing = [a for a in APPS if ready.get(a, 0) < 1]
    if missing:
        pytest.fail(f"Prerequisite: deploy k8s/*.yaml to {CTX} (not available: {missing})")


def pod(app):
    (p,) = [p for p in jget("-n", NS, "get", "pods", "-l", f"app={app},pod-template-hash")["items"]
            if p["status"]["phase"] == "Running"]
    return p


def test_pods_hardened_at_runtime(deployed):
    for app in APPS:
        p = pod(app)
        spec, (c,) = p["spec"], p["spec"]["containers"]
        assert spec["automountServiceAccountToken"] is False, app
        assert spec["securityContext"]["runAsNonRoot"] is True, app
        assert spec["securityContext"]["seccompProfile"]["type"] == "RuntimeDefault", app
        assert c["securityContext"]["readOnlyRootFilesystem"] is True, app
        assert c["securityContext"]["allowPrivilegeEscalation"] is False, app
        assert c["securityContext"]["capabilities"]["drop"] == ["ALL"], app
        assert not any(v.get("projected") or v.get("secret") for v in spec.get("volumes", [])), app
    assert kubectl("-n", NS, "exec", "deploy/agent", "--", "id", "-u").stdout.strip() == "10001"
    assert kubectl("-n", NS, "exec", "deploy/filesystem-mcp", "--", "id", "-u").stdout.strip() == "1000"
    labels = jget("get", "namespace", NS)["metadata"]["labels"]
    assert labels.get("pod-security.kubernetes.io/enforce") == "restricted"


def test_secret_has_only_the_two_keys_and_reaches_only_the_agent(deployed):
    secret = jget("-n", NS, "get", "secret", "agent-secrets")
    assert set(secret["data"]) <= {"LLM_API_KEY", "GITHUB_PERSONAL_ACCESS_TOKEN"}
    assert "kubectl.kubernetes.io/last-applied-configuration" not in (secret["metadata"].get("annotations") or {})
    for app in ("github-mcp", "filesystem-mcp"):
        assert "agent-secrets" not in json.dumps(pod(app)["spec"]), app
    # Values in the agent match .env: compared as hashes, nothing printed.
    code = "import os,hashlib;print(' '.join(hashlib.sha256(os.environ.get(k,'').encode()).hexdigest() for k in ('LLM_API_KEY','GITHUB_PERSONAL_ACCESS_TOKEN')))"
    in_pod = kubectl("-n", NS, "exec", "deploy/agent", "--", "python", "-c", code).stdout.split()
    if not secret_values():
        pytest.skip("no .env secrets on this machine to compare with")
    from dotenv import dotenv_values

    env = dotenv_values(REPO / ".env")
    expected = [hashlib.sha256((env.get(k) or "").encode()).hexdigest() for k in ("LLM_API_KEY", "GITHUB_PERSONAL_ACCESS_TOKEN")]
    assert in_pod == expected, "agent env doesn't match .env (re-run k8s/create_secret.py and restart the agent)"


@pytest.fixture(scope="module")
def probe(deployed):
    r = kubectl("-n", NS, "exec", "-i", "deploy/agent", "--", "python", "-", input=PROBE.read_text(), timeout=300)
    assert r.returncode == 0, f"probe failed: {r.stderr[-800:]}"
    return parse_probe(r.stdout)


def test_mcp_over_http_from_agent_pod(probe):
    """Same checks as compose, through the Service names in the cluster."""
    check_probe(probe)
    if not probe["github_enabled"]:
        pytest.skip("GitHub checks need GITHUB_PERSONAL_ACCESS_TOKEN in agent-secrets (filesystem checks passed)")


def test_agent_run_through_port_forward(deployed):
    # Local port chosen by kubectl; the process is ours and is stopped below.
    pf = subprocess.Popen(["kubectl", "--context", CTX, "-n", NS, "port-forward", "--address", "127.0.0.1", "svc/agent", ":8000"],
                          stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True)
    try:
        m = re.search(r"127\.0\.0\.1:(\d+)", pf.stdout.readline())
        assert m, "port-forward didn't start"
        base = f"http://127.0.0.1:{m.group(1)}"
        with urllib.request.urlopen(f"{base}/health", timeout=10) as r:
            assert json.load(r) == {"status": "ok"}
        provider = jget("-n", NS, "get", "configmap", "agent-config")["data"].get("LLM_PROVIDER", "mock")
        if provider != "mock":
            pytest.skip(f"LLM_PROVIDER={provider}: skipped to avoid a paid LLM call")
        req = urllib.request.Request(f"{base}/api/agent/run", method="POST", data=b'{"message": "live k8s test"}',
                                     headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=120) as r:
            assert "live k8s test" in json.load(r)["response"]
    finally:
        pf.terminate()
        pf.wait(timeout=10)


# --- NetworkPolicy enforcement -------------------------------------------

_POD = {"automountServiceAccountToken": False, "terminationGracePeriodSeconds": 1,  # sleep ignores SIGTERM
        "securityContext": {"runAsNonRoot": True, "runAsUser": 10001, "seccompProfile": {"type": "RuntimeDefault"}}}
_C = {"image": "busybox:1.36.1", "command": ["sleep", "1800"],
      "securityContext": {"allowPrivilegeEscalation": False, "readOnlyRootFilesystem": True, "capabilities": {"drop": ["ALL"]}}}
# name, namespace, labels, never-ready. The github-mcp stand-in gets that
# pod's policies (github-mcp's image has no shell to test from); never
# Ready, so the Service never sends it traffic.
_TEMP_PODS = [("live-outsider", "default", "role=live-test", False),
              ("live-probe", NS, "role=live-test", False),
              ("live-gh-standin", NS, "app=github-mcp,role=live-test", True)]


@pytest.fixture(scope="module")
def net(deployed):
    if kubectl("-n", NS, "get", "networkpolicy", "default-deny-all").returncode != 0:
        pytest.skip(f"NetworkPolicies not applied on {CTX}: isolation NOT ENFORCED here (use kind + Calico, README 8f)")
    for name, ns, labels, never_ready in _TEMP_PODS:
        c = dict(_C, name="c")
        if never_ready:
            c["readinessProbe"] = {"exec": {"command": ["false"]}, "periodSeconds": 5}
        kubectl("-n", ns, "delete", "pod", name, "--ignore-not-found", "--wait=true")
        r = kubectl("-n", ns, "run", name, "--image=busybox:1.36.1", "--restart=Never", f"--labels={labels}",
                    "--overrides", json.dumps({"spec": dict(_POD, containers=[c])}))
        assert r.returncode == 0, r.stderr
    for name, ns, _, _ in _TEMP_PODS:
        kubectl("-n", ns, "wait", "--for=jsonpath={.status.phase}=Running", f"pod/{name}", "--timeout=180s", timeout=200)
    ips = {f"{a}_svc": jget("-n", NS, "get", "svc", a)["spec"]["clusterIP"] for a in APPS}
    ips |= {f"{a}_pod": pod(a)["status"]["podIP"] for a in APPS}
    ips["api_svc"] = jget("get", "svc", "kubernetes")["spec"]["clusterIP"]
    ips["node"] = jget("get", "nodes")["items"][0]["status"]["addresses"][0]["address"]
    ips["dns_svc"] = jget("-n", "kube-system", "get", "svc", "kube-dns")["spec"]["clusterIP"]
    ips["dns_pod"] = jget("-n", "kube-system", "get", "pods", "-l", "k8s-app=kube-dns")["items"][0]["status"]["podIP"]
    time.sleep(5)  # NotReady stand-in out of the Service endpoints, policies on the new pods
    yield ips
    for name, ns, _, _ in _TEMP_PODS:
        kubectl("-n", ns, "delete", "pod", name, "--ignore-not-found", "--wait=false")


_NODE_TCP = ("const s=require('net').connect({host:process.argv[1],port:+process.argv[2],timeout:4000});"
             "s.on('connect',()=>process.exit(0));s.on('timeout',()=>process.exit(1));s.on('error',()=>process.exit(1))")
_PY_TCP = "import socket,sys; socket.create_connection((sys.argv[1],int(sys.argv[2])),4)"
_FROM = {  # how to open a TCP connection from each source
    "agent": [NS, "deploy/agent", "python", "-c", _PY_TCP],
    "filesystem-mcp": [NS, "deploy/filesystem-mcp", "node", "-e", _NODE_TCP],
    "github-mcp": [NS, "live-gh-standin", "nc", "-z", "-w", "4"],
    "unlabeled pod": [NS, "live-probe", "nc", "-z", "-w", "4"],
    "other namespace": ["default", "live-outsider", "nc", "-z", "-w", "4"],
}


def reach(src, host, port) -> bool:
    ns, target, *cmd = _FROM[src]
    return kubectl("-n", ns, "exec", target, "--", *cmd, host, str(port), timeout=60).returncode == 0


GITHUB_IP = "140.82.112.3"  # in GitHub's published "api" ranges
INTERNET_IP = "1.1.1.1"     # not GitHub

ALLOWED = [
    ("agent", "github-mcp_svc", 8082), ("agent", "github-mcp", 8082),
    ("agent", "filesystem-mcp_svc", 8000), ("agent", "filesystem-mcp", 8000),
    ("github-mcp", "api.github.com", 443), ("github-mcp", GITHUB_IP, 443),
]
BLOCKED = [
    *[("other namespace", f"{a}_{k}", p) for a, p in (("agent", 8000), ("github-mcp", 8082), ("filesystem-mcp", 8000)) for k in ("svc", "pod")],
    ("unlabeled pod", "agent_pod", 8000), ("unlabeled pod", "github-mcp_pod", 8082), ("unlabeled pod", "filesystem-mcp_pod", 8000),
    ("filesystem-mcp", INTERNET_IP, 443), ("filesystem-mcp", GITHUB_IP, 443), ("filesystem-mcp", "github-mcp_svc", 8082),
    ("filesystem-mcp", "github-mcp_pod", 8082), ("filesystem-mcp", "agent_pod", 8000), ("filesystem-mcp", "dns_svc", 53),
    ("filesystem-mcp", "api_svc", 443),
    ("agent", "api_svc", 443), ("agent", "node", 6443), ("agent", "node", 10250), ("agent", "dns_pod", 9153),
    ("agent", INTERNET_IP, 443), ("agent", GITHUB_IP, 443),
    ("github-mcp", GITHUB_IP, 80), ("github-mcp", INTERNET_IP, 443), ("github-mcp", "filesystem-mcp_pod", 8000),
    ("github-mcp", "agent_pod", 8000), ("github-mcp", "api_svc", 443), ("github-mcp", "node", 6443),
    ("github-mcp", "dns_pod", 9153),
]


def _host(net, target):
    return net.get(target, target)


@pytest.mark.parametrize("src,target,port", ALLOWED, ids=[f"{s}->{t}:{p}" for s, t, p in ALLOWED])
def test_allowed_path(net, src, target, port):
    assert reach(src, _host(net, target), port), f"{src} -> {target}:{port} should be allowed"


@pytest.mark.parametrize("src,target,port", BLOCKED, ids=[f"{s}->{t}:{p}" for s, t, p in BLOCKED])
def test_blocked_path(net, src, target, port):
    assert not reach(src, _host(net, target), port), f"{src} -> {target}:{port} is NOT blocked"


# Controls: a "blocked" above only means something if the target is
# actually listening. The outsider pod has no policy of its own, and
# non-mcp-agent targets aren't protected by ours, so it must reach them.
_CONTROLS = sorted({(t, p) for _, t, p in BLOCKED if not t.endswith(("_pod", "_svc")) or t in ("api_svc", "dns_svc", "dns_pod")})


@pytest.mark.parametrize("target,port", _CONTROLS, ids=[f"{t}:{p}" for t, p in _CONTROLS])
def test_control_blocked_targets_are_reachable_without_policy(net, target, port):
    assert reach("other namespace", _host(net, target), port), f"control: {target}:{port} unreachable even without policy"
