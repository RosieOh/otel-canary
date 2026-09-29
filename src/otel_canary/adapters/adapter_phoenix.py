"""arize-phoenix-otel: `phoenix.otel.register()` with an explicit HTTP endpoint and header."""


def run(endpoint: str, transport: str) -> None:
    from phoenix.otel import register

    tracer_provider = register(
        project_name="otel-canary",
        endpoint=f"{endpoint}/v1/traces",
        headers={"authorization": "Bearer otel-canary"},
        batch=False,
        set_global_tracer_provider=False,
        verbose=False,
    )
    with tracer_provider.get_tracer("otel-canary").start_as_current_span("smoke"):
        pass
    tracer_provider.force_flush()
