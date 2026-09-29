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

# Core packages that share the 1.x version number; force mode pins each of them.
_CORE_VERSIONED = (
    "opentelemetry-api",
    "opentelemetry-sdk",
    "opentelemetry-proto",
    "opentelemetry-exporter-otlp",
    "opentelemetry-exporter-otlp-proto-common",
    "opentelemetry-exporter-otlp-proto-http",
    "opentelemetry-exporter-otlp-proto-grpc",
)
# Released alongside core with the 0.x numbering (1.45.0 ↔ 0.66b0); instrumentation pins
# semantic-conventions exactly, so both have to move together.
_CONTRIB_VERSIONED = ("opentelemetry-semantic-conventions", "opentelemetry-instrumentation")

CORE_REPO = "https://github.com/open-telemetry/opentelemetry-python.git"
CONTRIB_REPO = "https://github.com/open-telemetry/opentelemetry-python-contrib.git"
# Requirement (with the extras the exporter depends on) -> subdirectory in the core repo.
_CORE_MAIN = {
    "opentelemetry-api": "opentelemetry-api",
    "opentelemetry-sdk": "opentelemetry-sdk",
    "opentelemetry-semantic-conventions": "opentelemetry-semantic-conventions",
    "opentelemetry-proto": "opentelemetry-proto",
    "opentelemetry-exporter-otlp": "exporter/opentelemetry-exporter-otlp",
    "opentelemetry-exporter-otlp-common": "exporter/opentelemetry-exporter-otlp-common",
    "opentelemetry-exporter-otlp-proto-common": "exporter/opentelemetry-exporter-otlp-proto-common",
    "opentelemetry-exporter-otlp-proto-http": "exporter/opentelemetry-exporter-otlp-proto-http",
    "opentelemetry-exporter-otlp-proto-grpc": "exporter/opentelemetry-exporter-otlp-proto-grpc",
    # The exporter asks for this extra; an override without it silently drops urllib3.
    "opentelemetry-exporter-http-transport[urllib3]": "exporter/opentelemetry-exporter-http-transport",
}
_CONTRIB_MAIN = {"opentelemetry-instrumentation": "opentelemetry-instrumentation"}


@dataclass
class InstallOutcome:
    status: str  # "ok", "blocked" or "infra"
    python: Path | None = None
    versions: dict[str, str] = field(default_factory=dict)
    log: str = ""


def otel_requirements(version: str, transport: str = "http") -> list[str]:
    packages = _OTEL_HTTP + (_OTEL_GRPC if transport == "grpc" else ())
    return [f"{package}=={version}" for package in packages]


def contrib_version(core_version: str) -> str:
    """The 0.x release that ships with a core release: 1.45.0 -> 0.66b0, 1.42.1 -> 0.63b1."""
    major, minor, patch = (int(part) for part in core_version.split("."))
    if major != 1:
        raise ValueError(f"unexpected OpenTelemetry version {core_version}")
    return f"0.{minor + 21}b{patch}"


def force_overrides(version: str) -> list[str]:
    """Pins that replace the SDK's own OpenTelemetry bounds (force mode, docs/DESIGN.md §4)."""
    contrib = contrib_version(version)
    return [f"{package}=={version}" for package in _CORE_VERSIONED] + [
        f"{package}=={contrib}" for package in _CONTRIB_VERSIONED
    ]


def main_overrides(core_ref: str = "main", contrib_ref: str = "main") -> list[str]:
    """Overrides that install core and contrib from git at the given refs (docs/DESIGN.md §8)."""
    core = [
        f"{requirement} @ git+{CORE_REPO}@{core_ref}#subdirectory={subdirectory}"
        for requirement, subdirectory in _CORE_MAIN.items()
    ]
    contrib = [
        f"{requirement} @ git+{CONTRIB_REPO}@{contrib_ref}#subdirectory={subdirectory}"
        for requirement, subdirectory in _CONTRIB_MAIN.items()
    ]
    return core + contrib


# Builds each installed OTLP exporter, which is where missing transport dependencies surface
# (urllib3 is imported when the exporter builds its transport, not when the module loads).
_STACK_CHECK = """
import importlib, importlib.util, sys
http = ("opentelemetry.exporter.otlp.proto.http.trace_exporter", {"endpoint": "http://127.0.0.1:9/v1/traces"})
grpc = ("opentelemetry.exporter.otlp.proto.grpc.trace_exporter",
        {"endpoint": "http://127.0.0.1:9", "insecure": True})
checks = [http, grpc] if sys.argv[1] == "grpc" else [http]
for module, kwargs in checks:
    try:
        spec = importlib.util.find_spec(module)
    except ModuleNotFoundError:
        spec = None
    if spec is not None:
        importlib.import_module(module).OTLPSpanExporter(**kwargs)
"""


def otel_stack_error(python: Path, transport: str, timeout: float = 120) -> str | None:
    """Why the installed OpenTelemetry exporters can't be built on their own, or None if they can.

    `uv pip check` is no help here: it doesn't notice a dropped extra, and in force mode it
    reports the SDK bounds the override is meant to ignore.
    """
    try:
        proc = subprocess.run(
            [str(python), "-c", _STACK_CHECK, transport], capture_output=True, text=True, timeout=timeout
        )
    except subprocess.TimeoutExpired:
        return "the OpenTelemetry exporter check timed out"
    if proc.returncode == 0:
        return None
    lines = [line for line in proc.stderr.strip().splitlines() if line.strip()]
    return lines[-1] if lines else f"exited with code {proc.returncode}"


def is_resolution_conflict(output: str) -> bool:
    return any(marker in output for marker in _CONFLICT_MARKERS)


def parse_freeze(output: str) -> dict[str, str]:
    """name -> version; packages installed from git show as git@<commit>."""
    versions = {}
    for line in output.splitlines():
        line = line.strip()
        if " @ git+" in line:
            name, _, url = line.partition(" @ ")
            commit = url.split("#")[0].rsplit("@", 1)[-1]
            versions[name.lower()] = f"git@{commit[:12]}"
            continue
        name, sep, version = line.partition("==")
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
