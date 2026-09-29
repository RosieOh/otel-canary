"""logfire: the SDK's own export path to the receiver (docs/adapters.md).

Pointing `AdvancedOptions(base_url=...)` at the receiver exercises the exporter Logfire uses for
its own backend, with its custom requests session and gzip. The generic OTEL_EXPORTER_OTLP_*
route would only exercise a plain OTLPSpanExporter.
"""


def run(endpoint: str, transport: str) -> None:
    import logfire

    logfire.configure(
        token="pylf_v1_us_otelcanary",
        send_to_logfire=True,
        console=False,
        advanced=logfire.AdvancedOptions(base_url=endpoint),
    )
    with logfire.span("smoke"):
        pass
    logfire.force_flush()
