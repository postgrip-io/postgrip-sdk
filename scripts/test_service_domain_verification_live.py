#!/usr/bin/env python3
"""Opt-in live verification against an explicitly disposable Service domain.

This test never creates, edits, or deletes a Service, environment, deployment,
or domain. It only performs the verification mutation under test and reads the
result. The dedicated variable name is intentional: callers must not point a
generic production-domain fixture at this script by accident.
"""

from __future__ import annotations

import argparse
from collections.abc import Mapping
import os
from pathlib import Path
import sys
import uuid
from urllib.parse import urlparse


ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "python" / "src"))

from postgrip.service import ServiceClient  # noqa: E402


def required(environ: Mapping[str, str], name: str) -> str:
    value = environ.get(name, "").strip()
    if not value:
        raise SystemExit(f"set {name} to run the disposable domain verification test")
    return value


def load_settings(environ: Mapping[str, str]) -> tuple[str, str, str, str, str]:
    if environ.get("POSTGRIP_SERVICE_DOMAIN_LIVE_DISPOSABLE", "").lower() != "true":
        raise SystemExit("POSTGRIP_SERVICE_DOMAIN_LIVE_DISPOSABLE=true is required")
    base_url = required(environ, "POSTGRIP_SERVICE_URL")
    parsed = urlparse(base_url)
    if (
        parsed.scheme != "https"
        or not parsed.netloc
        or parsed.username
        or parsed.password
        or "?" in base_url
        or "#" in base_url
        or parsed.query
        or parsed.fragment
    ):
        raise SystemExit(
            "POSTGRIP_SERVICE_URL must be an HTTPS origin without credentials, query, or fragment"
        )
    token = required(environ, "POSTGRIP_TOKEN")
    service_id = required(environ, "POSTGRIP_SERVICE_ID")
    environment_id = required(environ, "POSTGRIP_SERVICE_ENVIRONMENT_ID")
    domain_id = required(environ, "POSTGRIP_SERVICE_DISPOSABLE_DOMAIN_ID")
    for name, value in (
        ("POSTGRIP_SERVICE_ID", service_id),
        ("POSTGRIP_SERVICE_ENVIRONMENT_ID", environment_id),
        ("POSTGRIP_SERVICE_DISPOSABLE_DOMAIN_ID", domain_id),
    ):
        try:
            uuid.UUID(value)
        except ValueError as exc:
            raise SystemExit(f"{name} must be a UUID") from exc
    if environ.get("POSTGRIP_CONFIRM_DISPOSABLE_DOMAIN", "") != domain_id:
        raise SystemExit(
            "POSTGRIP_CONFIRM_DISPOSABLE_DOMAIN must exactly match "
            "POSTGRIP_SERVICE_DISPOSABLE_DOMAIN_ID"
        )
    return base_url.rstrip("/"), token, service_id, environment_id, domain_id


def self_test() -> None:
    domain_id = "00000000-0000-4000-8000-000000000003"
    fixture = {
        "POSTGRIP_SERVICE_DOMAIN_LIVE_DISPOSABLE": "true",
        "POSTGRIP_SERVICE_URL": "https://services.example.test",
        "POSTGRIP_TOKEN": "redacted",
        "POSTGRIP_SERVICE_ID": "00000000-0000-4000-8000-000000000001",
        "POSTGRIP_SERVICE_ENVIRONMENT_ID": "00000000-0000-4000-8000-000000000002",
        "POSTGRIP_SERVICE_DISPOSABLE_DOMAIN_ID": domain_id,
        "POSTGRIP_CONFIRM_DISPOSABLE_DOMAIN": domain_id,
    }
    load_settings(fixture)
    for unsafe in (
        {**fixture, "POSTGRIP_SERVICE_DOMAIN_LIVE_DISPOSABLE": "false"},
        {**fixture, "POSTGRIP_CONFIRM_DISPOSABLE_DOMAIN": "different"},
        {**fixture, "POSTGRIP_SERVICE_URL": "http://services.example.test"},
        {**fixture, "POSTGRIP_SERVICE_URL": "https://services.example.test?target=other"},
        {**fixture, "POSTGRIP_SERVICE_URL": "https://services.example.test#other"},
    ):
        try:
            load_settings(unsafe)
        except SystemExit:
            pass
        else:
            raise AssertionError("disposable Service domain guard did not fail")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--self-test", action="store_true")
    parser.add_argument("--validate-only", action="store_true")
    args = parser.parse_args()
    if args.self_test:
        self_test()
        print("Disposable Service domain live-suite safety self-test passed")
        return 0
    base_url, token, service_id, environment_id, domain_id = load_settings(os.environ)
    if args.validate_only:
        print("Disposable Service domain live-suite configuration is valid")
        return 0

    client = ServiceClient(base_url=base_url, token=token)
    result = client.administration.domains.verify_service_domain(
        service_id,
        environment_id,
        domain_id,
        idempotency_key=f"domain-live-{uuid.uuid4()}",
    )
    if result["outcome"] != "verified":
        raise SystemExit(f"public domain verification failed: {result.get('failureCode', 'unknown')}")
    for layer in ("dns", "tls", "route", "http"):
        if result[layer]["status"] != "passed":
            raise SystemExit(f"{layer} observation did not pass")

    observed = client.administration.domains.get_service_domain_verification(
        service_id,
        environment_id,
        domain_id,
    )
    if observed["id"] != result["id"]:
        raise SystemExit("latest observation does not match the completed verification")
    if observed["deploymentId"] != result["deploymentId"]:
        raise SystemExit("persisted observation deployment changed")
    if observed["domainConfigurationVersion"] != result["domainConfigurationVersion"]:
        raise SystemExit("persisted observation configuration version changed")

    print(
        "Disposable Service domain verification passed "
        f"(deployment={result['deploymentId']}, version={result['domainConfigurationVersion']})"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
