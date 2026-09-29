"""Command line entry point: `otel-canary run | plan | report`."""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

from otel_canary import matrix, report
from otel_canary.adapters import ADAPTERS, adapter_for_package
from otel_canary.runner import Cell, run_cell

EXIT_CODES = {"PASS": 0, "FAIL": 1, "DEGRADED": 2, "BLOCKED": 3, "INFRA": 4}
EXIT_USAGE = 64

_REQUIREMENT = re.compile(r"^([A-Za-z0-9][A-Za-z0-9._-]*)(?:==([A-Za-z0-9.+!_-]+))?$")


def parse_requirement(text: str) -> tuple[str, str | None]:
    """Split "name==version" (or a bare "name") into its parts."""
    match = _REQUIREMENT.match(text.strip())
    if not match:
        raise ValueError(f'expected "name" or "name==version", got "{text}"')
    return match.group(1), match.group(2)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="otel-canary",
        description="Check that LLM observability SDKs work with a given OpenTelemetry Python release.",
    )
    commands = parser.add_subparsers(dest="command", required=True)

    run = commands.add_parser(
        "run", help="install one SDK with one OpenTelemetry release and send a span to a mock receiver"
    )
    known = ", ".join(sorted(spec.package for spec in ADAPTERS.values()))
    run.add_argument(
        "--sdk", required=True, help=f'SDK requirement, e.g. "arize-phoenix-otel==0.17.1" ({known})'
    )
    run.add_argument("--otel", required=True, help="OpenTelemetry Python release, e.g. 1.45.0")
    run.add_argument("--transport", choices=["http", "grpc"], default="http")
    run.add_argument("--python", default="3.12", help="Python version for the cell (default: 3.12)")
    run.add_argument("--timeout", type=float, default=180, help="seconds allowed for the adapter to run")
    run.add_argument("--output", type=Path, help="also write the result JSON to this file")
    run.add_argument("--label", default="", help='role of the OTel version in a matrix, e.g. "latest"')
    run.add_argument("--exit-zero", action="store_true", help="exit 0 whatever the status (for matrix jobs)")

    commands.add_parser(
        "plan", help="print the matrix (latest SDKs × previous and latest OTel) as one line of JSON"
    )

    rep = commands.add_parser("report", help="merge cell results into a dashboard and a list of changes")
    rep.add_argument("results", type=Path, help="directory with one result JSON per cell")
    rep.add_argument("--previous", type=Path, help="results.json from the previous run")
    rep.add_argument("--out", type=Path, required=True, help="directory to write the site to")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    if args.command == "plan":
        print(json.dumps({"include": matrix.plan()}, separators=(",", ":")))
        return 0
    if args.command == "report":
        print(json.dumps(report.write_report(args.results, args.previous, args.out), indent=2))
        return 0
    return _run(args)


def _run(args: argparse.Namespace) -> int:
    try:
        package, _version = parse_requirement(args.sdk)
    except ValueError as exc:
        print(f"otel-canary: {exc}", file=sys.stderr)
        return EXIT_USAGE
    spec = adapter_for_package(package)
    if spec is None:
        print(f"otel-canary: no adapter for {package}", file=sys.stderr)
        return EXIT_USAGE
    if args.transport not in spec.transports:
        print(f"otel-canary: the {spec.name} adapter doesn't support {args.transport}", file=sys.stderr)
        return EXIT_USAGE

    cell = Cell(
        adapter=spec.name,
        sdk=args.sdk,
        otel=args.otel,
        transport=args.transport,
        python=args.python,
        label=args.label or args.otel,
    )
    result = run_cell(cell, timeout=args.timeout)
    text = json.dumps(result, indent=2)
    print(text)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text + "\n")
    return 0 if args.exit_zero else EXIT_CODES[result["status"]]


if __name__ == "__main__":
    sys.exit(main())
