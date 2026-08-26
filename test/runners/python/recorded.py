#!/usr/bin/env python3
from __future__ import annotations

import argparse
import base64
import json
from pathlib import Path

from postgrip.agent import Client as AgentClient
from postgrip.agent import Connection
from postgrip.agent.openapi import OperationId as AgentOperationId
from postgrip.service import ServiceClient
from postgrip.service.openapi import OperationId as ServiceOperationId
from postgrip.worker import WorkerClient
from postgrip.worker.openapi import OperationId as WorkerOperationId


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--fixture-root", required=True, type=Path)
    parser.add_argument("--plane", choices=("all", "agent", "worker", "service"), default="all")
    args = parser.parse_args()

    import os

    token = os.environ["POSTGRIP_TOKEN"]
    connection = Connection(
        args.base_url,
        auth_token=token,
        agent_id="recorded-agent",
        agent_access_token=os.environ["POSTGRIP_AGENT_ACCESS_TOKEN"],
        agent_access_expires_at="2099-01-01T00:00:00Z",
        agent_signing_private_key=os.environ["POSTGRIP_AGENT_SIGNING_PRIVATE_KEY"],
    )
    agent = AgentClient(connection)
    workers = WorkerClient(
        base_url=args.base_url, token=token, insecure_development=True,
    )
    services = ServiceClient(
        base_url=args.base_url, token=token, insecure_development=True,
    )

    completed: list[str] = []
    planes = ("agent", "worker", "service") if args.plane == "all" else (args.plane,)
    for plane in planes:
        for path in sorted((args.fixture_root / plane).glob("*.json")):
            fixture = json.loads(path.read_text(encoding="utf-8"))
            operation_id = fixture["operationId"]
            request = fixture["request"]
            if operation_id == "connectSandboxSession":
                continue
            if operation_id == "uploadWorkspace":
                agent.sandbox.upload_workspace(
                    base64.b64decode(request["streamBodyBase64"]),
                    repository_name=request["headers"].get("X-PostGrip-Repository"),
                    revision=request["headers"].get("X-PostGrip-Revision"),
                )
            elif plane == "agent":
                connection.openapi.request(
                    AgentOperationId(operation_id),
                    request["body"],
                    path_parameters=request["pathParameters"],
                    query=request["query"],
                    headers=request["headers"],
                )
            elif plane == "worker":
                workers.openapi.request(
                    WorkerOperationId(operation_id),
                    request["body"],
                    path_parameters=request["pathParameters"],
                    query=request["query"],
                    headers=request["headers"],
                )
            else:
                services.openapi.request(
                    ServiceOperationId(operation_id),
                    request["body"],
                    path_parameters=request["pathParameters"],
                    query=request["query"],
                    headers=request["headers"],
                )
            completed.append(operation_id)
    print(json.dumps({"language": "python", "operations": completed}))


if __name__ == "__main__":
    main()
