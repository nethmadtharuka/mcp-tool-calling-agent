"""Phase 8: static checks on the Kubernetes manifests. No cluster needed."""

import importlib.util
from pathlib import Path

import yaml

_K8S = Path(__file__).resolve().parents[1] / "k8s"


def _load(name):
    return yaml.safe_load((_K8S / name).read_text())


def test_namespace_enforces_restricted_pod_security():
    labels = _load("namespace.yaml")["metadata"]["labels"]
    assert labels["pod-security.kubernetes.io/enforce"] == "restricted"


def test_configmap_has_no_secrets_and_defaults_to_mock():
    data = _load("configmap.yaml")["data"]
    assert data["LLM_PROVIDER"] == "mock"
    assert not {"LLM_API_KEY", "GITHUB_PERSONAL_ACCESS_TOKEN"} & set(data)
    # URLs come from config.py defaults (the Service names), not here.
    assert not {"GITHUB_MCP_URL", "FILESYSTEM_MCP_URL"} & set(data)


def test_secret_holds_only_secret_keys():
    spec = importlib.util.spec_from_file_location("create_secret", _K8S / "create_secret.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)

    env = {"LLM_API_KEY": "k", "GITHUB_PERSONAL_ACCESS_TOKEN": "", "LLM_PROVIDER": "gemini"}
    secret = mod.build_secret(env)

    assert secret["stringData"] == {"LLM_API_KEY": "k"}  # empty and non-secret keys dropped
    assert secret["metadata"] == {"name": "agent-secrets", "namespace": "mcp-agent"}


# --- Workloads: every Deployment/Service under k8s/ ---


def _objects(kind):
    for path in _K8S.glob("*.yaml"):
        for doc in yaml.safe_load_all(path.read_text()):
            if doc and doc["kind"] == kind:
                yield doc


def test_every_deployment_is_hardened():
    deployments = list(_objects("Deployment"))
    assert deployments
    for d in deployments:
        name, pod = d["metadata"]["name"], d["spec"]["template"]["spec"]
        assert d["metadata"]["namespace"] == "mcp-agent", name
        assert pod["automountServiceAccountToken"] is False, name
        assert pod["securityContext"]["runAsNonRoot"] is True, name
        assert pod["securityContext"]["seccompProfile"] == {"type": "RuntimeDefault"}, name
        assert not {"hostNetwork", "hostPID", "hostIPC"} & set(pod), name
        assert all("hostPath" not in v for v in pod.get("volumes", [])), name
        for c in pod["containers"]:
            sc = c["securityContext"]
            assert sc["readOnlyRootFilesystem"] is True, name
            assert sc["allowPrivilegeEscalation"] is False, name
            assert sc["capabilities"] == {"drop": ["ALL"]}, name
            assert c["resources"]["limits"]["memory"], name
            assert ":latest" not in c["image"] and ("@sha256:" in c["image"] or ":" in c["image"]), name
            assert all("hostPort" not in p for p in c.get("ports", [])), name


def test_services_are_internal_only():
    for s in _objects("Service"):
        assert s["spec"].get("type", "ClusterIP") == "ClusterIP", s["metadata"]["name"]


def test_github_mcp_is_read_only_and_gets_no_secrets():
    (d,) = [d for d in _objects("Deployment") if d["metadata"]["name"] == "github-mcp"]
    (c,) = d["spec"]["template"]["spec"]["containers"]
    assert "--read-only" in c["args"]
    assert "@sha256:" in c["image"]
    assert "env" not in c and "envFrom" not in c  # the agent sends the PAT per request
    (s,) = [s for s in _objects("Service") if s["metadata"]["name"] == "github-mcp"]
    assert s["spec"]["ports"][0]["port"] == 8082  # matches GITHUB_MCP_URL default


_FS = _K8S.parent / "filesystem-mcp"


def test_filesystem_mcp_single_replica_local_image_no_secrets():
    (d,) = [d for d in _objects("Deployment") if d["metadata"]["name"] == "filesystem-mcp"]
    # supergateway --stateful sessions live in one pod's memory.
    assert d["spec"]["replicas"] == 1
    assert d["spec"]["strategy"]["type"] == "Recreate"
    (c,) = d["spec"]["template"]["spec"]["containers"]
    assert c["imagePullPolicy"] == "IfNotPresent"  # locally built: never pulled
    assert "env" not in c and "envFrom" not in c
    (s,) = [s for s in _objects("Service") if s["metadata"]["name"] == "filesystem-mcp"]
    assert s["spec"]["ports"][0]["port"] == 8000  # matches FILESYSTEM_MCP_URL default


def test_k8s_snapshot_build_context_is_an_allowlist_without_secrets():
    lines = [l.strip() for l in (_FS / "Dockerfile.k8s.dockerignore").read_text().splitlines()]
    rules = [l for l in lines if l and not l.startswith("#")]
    assert rules[0] == "*"  # exclude everything first
    included = {r[1:].rstrip("/").lower() for r in rules if r.startswith("!")}
    assert not included & {".env", ".git", ".venv", "build.log", ".pytest_cache", "."}
    assert not any(r.startswith("!") and ("*" in r or ".env" == r[1:].lower()) for r in rules)


def test_agent_config_and_secrets_wiring():
    (d,) = [d for d in _objects("Deployment") if d["metadata"]["name"] == "agent"]
    pod = d["spec"]["template"]["spec"]
    (c,) = pod["containers"]
    assert c["imagePullPolicy"] == "IfNotPresent"
    # Dockerfile's `useradd --uid 10001 app`
    assert pod["securityContext"]["runAsUser"] == 10001
    assert c["envFrom"] == [{"configMapRef": {"name": "agent-config"}}]
    refs = {e["name"]: e["valueFrom"]["secretKeyRef"] for e in c["env"]}
    assert set(refs) == {"LLM_API_KEY", "GITHUB_PERSONAL_ACCESS_TOKEN"}
    assert all(r["name"] == "agent-secrets" and r["key"] == n for n, r in refs.items())
    assert all("value" not in e for e in c["env"])  # never inline values
    for probe in ("readinessProbe", "livenessProbe"):
        assert c[probe]["httpGet"]["path"] == "/health"  # app/api/routes.py


def test_only_the_agent_gets_the_secret():
    for d in _objects("Deployment"):
        text = yaml.safe_dump(d)
        assert ("agent-secrets" in text) == (d["metadata"]["name"] == "agent"), d["metadata"]["name"]


# --- 8f: NetworkPolicy ---


def _policies():
    return list(_objects("NetworkPolicy"))


def test_default_deny_all_exists():
    deny = [p for p in _policies() if p["spec"]["podSelector"] == {}
            and set(p["spec"]["policyTypes"]) == {"Ingress", "Egress"}
            and not p["spec"].get("ingress") and not p["spec"].get("egress")]
    assert deny and deny[0]["metadata"]["namespace"] == "mcp-agent"


def _all_policies_including_optional():
    for path in _K8S.rglob("*.yaml"):
        for doc in yaml.safe_load_all(path.read_text()):
            if doc and doc.get("kind") == "NetworkPolicy":
                yield path.relative_to(_K8S).as_posix(), doc


def test_no_allow_all_rules():
    for path, p in _all_policies_including_optional():
        name = f"{path}:{p['metadata']['name']}"
        for rule in p["spec"].get("ingress", []):
            assert rule.get("from"), f"{name}: ingress rule without 'from' allows every source"
        for rule in p["spec"].get("egress", []):
            assert rule.get("to"), f"{name}: egress rule without 'to' allows every destination"
            assert rule.get("ports"), f"{name}: egress rule without ports allows every port"
        for rule in p["spec"].get("ingress", []) + p["spec"].get("egress", []):
            for peer in rule.get("from", []) + rule.get("to", []):
                # {} selectors match every pod / every namespace
                assert peer.get("namespaceSelector") != {}, f"{name}: matches all namespaces"
                assert not (set(peer) == {"podSelector"} and peer["podSelector"] == {}), f"{name}: matches all pods"


def test_only_the_optional_llm_policy_opens_the_internet():
    for path, p in _all_policies_including_optional():
        for rule in p["spec"].get("egress", []):
            for peer in rule["to"]:
                if peer.get("ipBlock", {}).get("cidr") == "0.0.0.0/0":
                    # Opt-in file, explained there: HTTPS to public IPs only.
                    assert path == "optional/agent-llm-egress.yaml", path
                    assert p["spec"]["podSelector"] == {"matchLabels": {"app": "agent"}}
                    assert rule["ports"] == [{"protocol": "TCP", "port": 443}]
                    assert {"10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16", "169.254.0.0/16"} <= set(peer["ipBlock"]["except"])


def test_every_workload_has_its_own_ingress_and_egress_policy():
    policies = _policies()
    for d in _objects("Deployment"):
        app = d["spec"]["template"]["metadata"]["labels"]["app"]
        own = [p for p in policies if p["spec"]["podSelector"].get("matchLabels") == {"app": app}]
        assert len(own) == 1, app
        assert set(own[0]["spec"]["policyTypes"]) == {"Ingress", "Egress"}, app


def test_mcp_servers_only_reachable_from_agent_and_filesystem_has_no_egress():
    by_name = {p["metadata"]["name"]: p["spec"] for p in _policies()}
    for name in ("github-mcp", "filesystem-mcp"):
        (rule,) = by_name[name]["ingress"]
        assert rule["from"] == [{"podSelector": {"matchLabels": {"app": "agent"}}}], name
    assert "egress" not in by_name["filesystem-mcp"]
    dns_apps = by_name["allow-dns"]["podSelector"]["matchExpressions"][0]["values"]
    assert "filesystem-mcp" not in dns_apps
    # github-mcp: HTTPS to fixed (GitHub) ranges only, never 0.0.0.0/0
    (egress,) = by_name["github-mcp"]["egress"]
    assert egress["ports"] == [{"protocol": "TCP", "port": 443}]
    assert all(set(peer) == {"ipBlock"} and peer["ipBlock"]["cidr"] != "0.0.0.0/0" for peer in egress["to"])


def test_kind_cluster_config_pins_node_image_and_disables_default_cni():
    cfg = yaml.safe_load((_K8S / "kind" / "cluster.yaml").read_text())
    assert cfg["networking"]["disableDefaultCNI"] is True  # Calico instead
    assert "@sha256:" in cfg["nodes"][0]["image"]


def test_k8s_dockerfile_pins_match_compose_dockerfile():
    def pins(name):
        text = (_FS / name).read_text()
        return [l for l in text.splitlines() if l.startswith("FROM ") or "supergateway@" in l]

    assert pins("Dockerfile.k8s") == pins("Dockerfile")
    assert "@sha256:" in pins("Dockerfile.k8s")[0]
