"""SDK adapters (docs/DESIGN.md §7, docs/adapters.md).

Each adapter is a module `adapter_<name>.py` in this directory with `run(endpoint, transport)`.
It is executed by `_runner.py` with the *cell's* Python, so these modules may import only the
standard library and the SDK under test, never `otel_canary`. The `adapter_` prefix keeps a
module from shadowing the SDK it tests (a `phoenix.py` here would hide the `phoenix` package).
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

ADAPTERS_DIR = Path(__file__).parent
RUNNER = ADAPTERS_DIR / "_runner.py"


@dataclass(frozen=True)
class AdapterSpec:
    name: str
    package: str
    transports: frozenset[str]
    # What a healthy export looks like at the receiver.
    expect_path: str | None = None
    expect_headers: tuple[str, ...] = ()
    min_spans: int = 1


ADAPTERS: dict[str, AdapterSpec] = {
    spec.name: spec
    for spec in (
        AdapterSpec(
            name="phoenix",
            package="arize-phoenix-otel",
            transports=frozenset({"http"}),
            expect_path="/v1/traces",
            expect_headers=("authorization",),
        ),
        AdapterSpec(
            name="langfuse",
            package="langfuse",
            transports=frozenset({"http"}),
            expect_path="/api/public/otel/v1/traces",
            expect_headers=("authorization",),
        ),
        AdapterSpec(
            name="traceloop",
            package="traceloop-sdk",
            transports=frozenset({"http"}),
            expect_path="/v1/traces",
            expect_headers=("authorization",),
        ),
    )
}


def adapter_for_package(package: str) -> AdapterSpec | None:
    normalized = package.lower().replace("_", "-")
    return next((spec for spec in ADAPTERS.values() if spec.package == normalized), None)
