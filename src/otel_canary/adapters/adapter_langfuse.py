"""langfuse: the client exports over OTLP/HTTP to `{base_url}/api/public/otel/v1/traces`."""


def run(endpoint: str, transport: str) -> None:
    from langfuse import Langfuse

    client = Langfuse(public_key="pk-lf-otel-canary", secret_key="sk-lf-otel-canary", base_url=endpoint)
    # v4 renamed start_as_current_span to start_as_current_observation.
    start = getattr(client, "start_as_current_observation", None) or client.start_as_current_span
    with start(name="smoke"):
        pass
    client.flush()
