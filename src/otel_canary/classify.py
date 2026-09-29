"""Cell verdicts: PASS / FAIL / DEGRADED / BLOCKED / INFRA (docs/DESIGN.md §6)."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Any

from otel_canary.adapters import AdapterSpec
from otel_canary.install import InstallOutcome
from otel_canary.receivers import ReceiverLog


class Status(StrEnum):
    PASS = "PASS"
    FAIL = "FAIL"
    DEGRADED = "DEGRADED"
    BLOCKED = "BLOCKED"
    INFRA = "INFRA"


@dataclass
class AdapterOutcome:
    exit_code: int | None
    timed_out: bool = False
    report: dict[str, Any] | None = None  # the JSON line _runner.py prints last
    stderr: str = ""


@dataclass
class Verdict:
    status: Status
    reason: str
    # An override-based install (force / main) can drop a dependency by itself, so a
    # ModuleNotFoundError there needs a look before anyone reports it upstream.
    suspect_install: bool = False


_NOISE = ("Using Python", "Resolved", "Prepared", "Installed", "Audited", "Uninstalled")


def _log_reason(text: str, keywords: tuple[str, ...]) -> str:
    """The log line with the earliest keyword that appears, else the first line that isn't noise.

    uv wraps the resolver's explanation over indented lines, so those are joined onto the match.
    """
    raw = text.splitlines()
    cleaned = [line.strip().lstrip("×╰─▶ ").strip() for line in raw]
    candidates = [i for i, line in enumerate(cleaned) if line and not line.startswith(_NOISE)]
    for keyword in keywords:  # keywords are in order of preference
        for i in candidates:
            if keyword not in cleaned[i]:
                continue
            parts = [cleaned[i]]
            for following, text_line in zip(raw[i + 1 :], cleaned[i + 1 :], strict=True):
                if not following.startswith((" ", "\t")) or not text_line:
                    break
                if following.strip().startswith(("×", "╰", "hint", "help")):
                    break
                parts.append(text_line)
            return " ".join(parts)
    return cleaned[candidates[0]] if candidates else ""


def classify(
    install: InstallOutcome,
    adapter: AdapterOutcome | None,
    received: ReceiverLog | None,
    spec: AdapterSpec,
    used_overrides: bool = False,
    transport: str = "http",
) -> Verdict:
    if install.status == "blocked":
        reason = _log_reason(install.log, ("Because", "No solution found"))
        return Verdict(Status.BLOCKED, reason or "the resolver found no solution")
    if install.status != "ok":
        reason = _log_reason(install.log, ("error", "Error", "failed", "Failed"))
        return Verdict(Status.INFRA, "install failed: " + (reason or "unknown error"))
    if adapter is None or received is None:
        return Verdict(Status.INFRA, "the adapter did not run")
    if adapter.timed_out:
        return Verdict(Status.INFRA, "the adapter timed out")

    report = adapter.report
    if report is None:
        return Verdict(Status.FAIL, f"the adapter exited with code {adapter.exit_code} without a report")
    if not report.get("ok"):
        error_type = report.get("error_type", "Error")
        return Verdict(
            Status.FAIL,
            f"{error_type}: {report.get('error', '')}",
            suspect_install=used_overrides and error_type == "ModuleNotFoundError",
        )

    if received.spans < spec.min_spans:
        return Verdict(Status.DEGRADED, f"expected at least {spec.min_spans} span(s), got {received.spans}")
    # The expected path is an HTTP detail; gRPC calls always go to the TraceService Export method.
    if transport == "http" and spec.expect_path and spec.expect_path not in received.accepted_paths():
        return Verdict(Status.DEGRADED, f"no spans arrived at {spec.expect_path}")
    missing = [header for header in spec.expect_headers if header not in received.accepted_headers()]
    if missing:
        return Verdict(Status.DEGRADED, "missing request headers: " + ", ".join(missing))
    return Verdict(Status.PASS, f"{received.spans} span(s) received")
