"""Which cells to run, with versions from PyPI (docs/DESIGN.md §4)."""

from __future__ import annotations

import json
import ssl
import urllib.request
from pathlib import Path
from typing import Any

from otel_canary.adapters import ADAPTERS

PYPI_JSON = "https://pypi.org/pypi/{name}/json"
LABELS = ("previous", "latest")


def _ssl_context() -> ssl.SSLContext:
    context = ssl.create_default_context()
    # Some standalone Python builds ship without a CA bundle; fall back to the system one.
    if not context.get_ca_certs() and Path("/etc/ssl/cert.pem").exists():
        context.load_verify_locations("/etc/ssl/cert.pem")
    return context


def fetch_releases(name: str) -> list[str]:
    with urllib.request.urlopen(PYPI_JSON.format(name=name), context=_ssl_context(), timeout=30) as resp:
        data = json.load(resp)
    # Skip releases that were yanked everywhere or have no files.
    return [
        version
        for version, files in data["releases"].items()
        if files and not all(file.get("yanked") for file in files)
    ]


def _final_key(version: str) -> tuple[int, ...] | None:
    """Sort key for final releases like 1.45.0; None for pre-releases and anything unusual."""
    parts = version.split(".")
    if not all(part.isdigit() for part in parts):
        return None
    return tuple(int(part) for part in parts)


def latest_final(versions: list[str]) -> str:
    finals = [v for v in versions if _final_key(v) is not None]
    return max(finals, key=lambda v: _final_key(v) or ())


def otel_versions(releases: list[str]) -> dict[str, str]:
    """The latest OpenTelemetry release and the last patch of the minor before it."""
    latest = latest_final(releases)
    latest_minor = (_final_key(latest) or ())[:2]
    older = [v for v in releases if (key := _final_key(v)) is not None and key[:2] < latest_minor]
    return {"previous": latest_final(older), "latest": latest}


def plan(
    otel: dict[str, str] | None = None,
    sdk_versions: dict[str, str] | None = None,
    fetch: Any = fetch_releases,
) -> list[dict[str, str]]:
    """One cell per adapter, transport and OTel label, each SDK at its latest release."""
    otel = otel or otel_versions(fetch("opentelemetry-sdk"))
    sdk_versions = sdk_versions or {
        spec.name: latest_final(fetch(spec.package)) for spec in ADAPTERS.values()
    }
    cells = []
    for spec in ADAPTERS.values():
        for transport in sorted(spec.transports):
            for label in LABELS:
                cells.append(
                    {
                        "id": f"{spec.name}-{transport}-{label}",
                        "adapter": spec.name,
                        "sdk": f"{spec.package}=={sdk_versions[spec.name]}",
                        "otel": otel[label],
                        "label": label,
                        "transport": transport,
                    }
                )
    return cells
