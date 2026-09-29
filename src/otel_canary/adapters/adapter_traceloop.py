"""traceloop-sdk: `Traceloop.init()` picks the HTTP exporter for http:// endpoints."""


def run(endpoint: str, transport: str) -> None:
    from opentelemetry import trace
    from traceloop.sdk import Traceloop
    from traceloop.sdk.decorators import workflow

    Traceloop.init(
        app_name="otel-canary",
        api_endpoint=endpoint,
        headers={"authorization": "Bearer otel-canary"},
        disable_batch=True,
        telemetry_enabled=False,  # otherwise the SDK reports usage to an external service
    )

    @workflow(name="smoke")
    def smoke() -> int:
        return 1

    smoke()
    trace.get_tracer_provider().force_flush()
