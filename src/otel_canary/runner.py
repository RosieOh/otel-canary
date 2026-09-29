"""Runs one cell end to end: virtualenv, install, mock receiver, adapter, verdict."""

from __future__ import annotations

import json
import os
import subprocess
import tempfile
import time
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from otel_canary.adapters import ADAPTERS, RUNNER, AdapterSpec
from otel_canary.classify import AdapterOutcome, classify
from otel_canary.install import (
    InstallOutcome,
    create_and_install,
    force_overrides,
    main_overrides,
    otel_requirements,
    otel_stack_error,
)
from otel_canary.receivers import GRPCReceiver, HTTPReceiver


@dataclass
class Cell:
    adapter: str
    sdk: str  # requirement, e.g. "arize-phoenix-otel==0.17.1"
    otel: str  # OpenTelemetry Python release, e.g. "1.45.0"
    transport: str = "http"
    python: str = "3.12"
    # "respect-pins" installs what users get; "force" overrides the SDK's OpenTelemetry bounds.
    mode: str = "respect-pins"
    # The OTel version's role in the matrix ("previous", "latest", "main"); results are compared by it.
    label: str = ""
    # With otel="main": the core and contrib commits to install.
    core_ref: str = ""
    contrib_ref: str = ""


def install_plan(cell: Cell) -> tuple[list[str], list[str] | None]:
    """Requirements and overrides for a cell. main and force install through overrides."""
    grpc_exporter = ["opentelemetry-exporter-otlp-proto-grpc"] if cell.transport == "grpc" else []
    if cell.otel == "main":
        return [cell.sdk, *grpc_exporter], main_overrides(cell.core_ref or "main", cell.contrib_ref or "main")
    if cell.mode == "force":
        return [cell.sdk, *grpc_exporter], force_overrides(cell.otel)
    return [cell.sdk, *otel_requirements(cell.otel, cell.transport)], None


def _cell_env(endpoint: str, transport: str) -> dict[str, str]:
    # Nothing from the harness environment should steer the SDK: drop OTEL_* settings and
    # anything that points Python at another environment.
    env = {
        key: value
        for key, value in os.environ.items()
        if not key.startswith("OTEL_") and key not in ("PYTHONPATH", "VIRTUAL_ENV", "PYTHONHOME")
    }
    env.update(CANARY_ENDPOINT=endpoint, CANARY_TRANSPORT=transport)
    return env


def _last_json_line(stdout: str) -> dict[str, Any] | None:
    for line in reversed(stdout.strip().splitlines()):
        try:
            parsed = json.loads(line)
        except ValueError:
            continue
        if isinstance(parsed, dict) and "ok" in parsed:
            return parsed
    return None


def run_adapter(
    python: Path, spec: AdapterSpec, endpoint: str, transport: str, workdir: Path, timeout: float
) -> AdapterOutcome:
    try:
        proc = subprocess.run(
            [str(python), str(RUNNER), spec.name],
            cwd=workdir,
            env=_cell_env(endpoint, transport),
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired as exc:
        stderr = exc.stderr.decode(errors="replace") if isinstance(exc.stderr, bytes) else exc.stderr or ""
        return AdapterOutcome(exit_code=None, timed_out=True, stderr=stderr[-4000:])
    return AdapterOutcome(proc.returncode, report=_last_json_line(proc.stdout), stderr=proc.stderr[-4000:])


def run_cell(cell: Cell, timeout: float = 180) -> dict[str, Any]:
    spec = ADAPTERS[cell.adapter]
    started = time.monotonic()
    started_at = datetime.now(UTC).isoformat(timespec="seconds")
    adapter_outcome = None
    received = None
    with tempfile.TemporaryDirectory(prefix="otel-canary-") as tmp:
        workdir = Path(tmp)
        requirements, overrides = install_plan(cell)
        install = create_and_install(workdir, cell.python, requirements, overrides)
        if overrides and install.status == "ok" and install.python is not None:
            error = otel_stack_error(install.python, cell.transport)
            if error:
                install = InstallOutcome(
                    "infra",
                    versions=install.versions,
                    log=f"the overridden OpenTelemetry packages fail on their own: {error}",
                )
        if install.status == "ok" and install.python is not None:
            receiver_cm = (
                GRPCReceiver() if cell.transport == "grpc" else HTTPReceiver(get_responses=spec.get_responses)
            )
            with receiver_cm as receiver:
                adapter_outcome = run_adapter(
                    install.python, spec, receiver.url, cell.transport, workdir, timeout
                )
                time.sleep(0.3)  # let a request that is still in flight land
                received = receiver.log
    verdict = classify(
        install, adapter_outcome, received, spec, used_overrides=bool(overrides), transport=cell.transport
    )

    adapter_log = ""
    if adapter_outcome is not None:
        traceback = (adapter_outcome.report or {}).get("traceback", "")
        adapter_log = (traceback or adapter_outcome.stderr)[-4000:]
    return {
        "cell": asdict(cell),
        "status": verdict.status.value,
        "reason": verdict.reason,
        "suspect_install": verdict.suspect_install,
        "received": received.summary() if received is not None else None,
        "versions": install.versions,
        "started_at": started_at,
        "duration_s": round(time.monotonic() - started, 1),
        "logs": {"install": install.log[-2000:], "adapter": adapter_log},
    }
