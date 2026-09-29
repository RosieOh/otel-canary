"""Per-cell virtualenvs and installs with uv (docs/DESIGN.md §5, §8)."""

from __future__ import annotations

import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

# The resolver prints this when the requested versions can't be installed together.
_CONFLICT_MARKERS = ("No solution found when resolving dependencies", "is unsatisfiable")

# Pinning these makes the resolver pick the requested OpenTelemetry release for everything else.
_OTEL_HTTP = ("opentelemetry-api", "opentelemetry-sdk", "opentelemetry-exporter-otlp-proto-http")
_OTEL_GRPC = ("opentelemetry-exporter-otlp-proto-grpc",)


@dataclass
class InstallOutcome:
    status: str  # "ok", "blocked" or "infra"
    python: Path | None = None
    versions: dict[str, str] = field(default_factory=dict)
    log: str = ""


def otel_requirements(version: str, transport: str = "http") -> list[str]:
    packages = _OTEL_HTTP + (_OTEL_GRPC if transport == "grpc" else ())
    return [f"{package}=={version}" for package in packages]


def is_resolution_conflict(output: str) -> bool:
    return any(marker in output for marker in _CONFLICT_MARKERS)


def parse_freeze(output: str) -> dict[str, str]:
    versions = {}
    for line in output.splitlines():
        name, sep, version = line.strip().partition("==")
        if sep:
            versions[name.lower()] = version
    return versions


def _run(cmd: list[str], timeout: float) -> subprocess.CompletedProcess[str]:
    return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)


def create_and_install(
    workdir: Path,
    python: str,
    requirements: list[str],
    overrides: list[str] | None = None,
    timeout: float = 600,
) -> InstallOutcome:
    """Create a virtualenv in `workdir` and install `requirements` into it.

    `overrides` are written to an override file for `uv pip install --override`. Callers must
    keep extras on overridden packages (for example `opentelemetry-exporter-http-transport[urllib3]`):
    an override replaces the whole requirement, so dropping an extra drops its dependencies and
    shows up as a fake ModuleNotFoundError (docs/DESIGN.md §8).
    """
    uv = shutil.which("uv")
    if uv is None:
        return InstallOutcome("infra", log="uv is not installed")

    venv = workdir / "venv"
    try:
        created = _run([uv, "venv", "--no-config", "--python", python, str(venv)], timeout)
    except subprocess.TimeoutExpired:
        return InstallOutcome("infra", log="uv venv timed out")
    if created.returncode != 0:
        return InstallOutcome("infra", log=created.stderr[-4000:])
    venv_python = venv / "bin" / "python"

    cmd = [uv, "pip", "install", "--no-config", "--python", str(venv_python), *requirements]
    if overrides:
        override_file = workdir / "overrides.txt"
        override_file.write_text("\n".join(overrides) + "\n")
        cmd += ["--override", str(override_file)]
    try:
        installed = _run(cmd, timeout)
    except subprocess.TimeoutExpired:
        return InstallOutcome("infra", log="uv pip install timed out")
    if installed.returncode != 0:
        output = installed.stderr + installed.stdout
        status = "blocked" if is_resolution_conflict(output) else "infra"
        return InstallOutcome(status, log=output[-4000:])

    frozen = _run([uv, "pip", "freeze", "--no-config", "--python", str(venv_python)], timeout)
    return InstallOutcome(
        "ok", python=venv_python, versions=parse_freeze(frozen.stdout), log=installed.stderr[-4000:]
    )
