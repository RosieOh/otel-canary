"""M1 acceptance: known cases must be judged correctly (issue #7).

The SDK versions are pinned, but their own dependencies are not, so a case can change if a
dependency starts pulling in a missing package. That would be worth knowing about too.
"""

import pytest

from otel_canary.adapters import adapter_for_package
from otel_canary.cli import parse_requirement
from otel_canary.runner import Cell, run_cell

GOLDEN = [
    # Phoenix #16547: register() read HTTPSpanExporter._headers, which 1.45 moved.
    ("arize-phoenix-otel==0.17.1", "1.45.0", "http", "FAIL", "_headers"),
    ("arize-phoenix-otel==0.17.2", "1.45.0", "http", "PASS", None),
    ("arize-phoenix-otel==0.17.2", "1.45.0", "grpc", "PASS", None),
    # traceloop/openllmetry#4526: requests and httpx are imported but not declared.
    ("traceloop-sdk==0.62.3", "1.45.0", "http", "FAIL", "requests"),
    ("traceloop-sdk==0.62.3", "1.44.0", "http", "FAIL", "httpx"),
    ("langfuse==4.15.6", "1.45.0", "http", "PASS", None),
    ("logfire==5.1.1", "1.44.0", "http", "PASS", None),
    # logfire caps OpenTelemetry below 1.45 (pydantic/logfire#2497 explains why it still needs to).
    ("logfire==5.1.1", "1.45.0", "http", "BLOCKED", "opentelemetry"),
    ("weave==0.53.11", "1.44.0", "http", "PASS", None),
]


@pytest.mark.integration
@pytest.mark.parametrize(("sdk", "otel", "transport", "expected", "reason_part"), GOLDEN)
def test_golden_cells(sdk, otel, transport, expected, reason_part):
    package, _ = parse_requirement(sdk)
    spec = adapter_for_package(package)
    assert spec is not None

    result = run_cell(Cell(adapter=spec.name, sdk=sdk, otel=otel, transport=transport))

    assert result["status"] == expected, result["reason"]
    if reason_part:
        assert reason_part in result["reason"]
