"""weave: conversation tracing through the private `_setup_conversation_tracing()`.

The public `weave.init()` needs a W&B account and server, so this calls the function it uses to
build the OTLP exporter. Being private, it can change without notice; a FAIL here needs a look at
whether the function moved before anyone reports it (docs/adapters.md).
"""


def run(endpoint: str, transport: str) -> None:
    import os

    os.environ["WF_TRACE_SERVER_URL"] = endpoint

    from opentelemetry import trace
    from weave.trace.weave_init import _setup_conversation_tracing

    _setup_conversation_tracing("otel-canary", "otel-canary", None)
    with trace.get_tracer("weave.conversation").start_as_current_span("smoke"):
        pass
    trace.get_tracer_provider().force_flush()
