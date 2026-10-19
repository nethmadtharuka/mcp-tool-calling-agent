"""Create/update the agent-secrets Secret from .env:  python k8s/create_secret.py

Extra arguments go to kubectl, e.g. `python k8s/create_secret.py --context kind-mcp-agent`.

Only the secret keys are copied (not LLM_PROVIDER etc., which belong in
the ConfigMap). Values are parsed like the app parses them (python-dotenv)
and piped to kubectl on stdin, so they never appear in command arguments,
shell history or a file on disk. Nothing is printed except key names.
"""

import json
import subprocess
import sys
from pathlib import Path

from dotenv import dotenv_values

SECRET_KEYS = ("LLM_API_KEY", "GITHUB_PERSONAL_ACCESS_TOKEN")


def build_secret(env: dict) -> dict:
    return {
        "apiVersion": "v1",
        "kind": "Secret",
        "metadata": {"name": "agent-secrets", "namespace": "mcp-agent"},
        "type": "Opaque",
        "stringData": {k: env[k] for k in SECRET_KEYS if env.get(k)},
    }


if __name__ == "__main__":
    secret = build_secret(dotenv_values(Path(__file__).resolve().parents[1] / ".env"))
    # --server-side: plain `kubectl apply` would also store the values in a
    # last-applied-configuration annotation.
    subprocess.run(
        ["kubectl", *sys.argv[1:], "apply", "--server-side", "-f", "-"],
        input=json.dumps(secret), text=True, check=True,
    )
    print("agent-secrets keys:", sorted(secret["stringData"]))
