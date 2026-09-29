"""Runs one adapter inside a cell's virtualenv and prints one JSON line as the last line of stdout.

Usage: <cell python> _runner.py <adapter name>, with CANARY_ENDPOINT and CANARY_TRANSPORT set.
Only the standard library is used here: otel_canary is not installed in the cell.
"""

import importlib
import json
import os
import sys
import traceback


def main() -> int:
    name = sys.argv[1]
    endpoint = os.environ["CANARY_ENDPOINT"]
    transport = os.environ.get("CANARY_TRANSPORT", "http")
    try:
        module = importlib.import_module(f"adapter_{name}")
        module.run(endpoint, transport)
    except BaseException as exc:  # report every failure, including SystemExit raised by an SDK
        report = {
            "ok": False,
            "error_type": type(exc).__name__,
            "error": str(exc)[:1000],
            "traceback": traceback.format_exc()[-6000:],
        }
        print(json.dumps(report), flush=True)
        return 1
    print(json.dumps({"ok": True}), flush=True)
    return 0


if __name__ == "__main__":
    code = main()
    sys.stdout.flush()
    sys.stderr.flush()
    # Exit without waiting for SDK background threads (batch processors, telemetry) to wind down.
    # The flush above matters: os._exit skips stdio buffers, which would otherwise lose the report.
    os._exit(code)
