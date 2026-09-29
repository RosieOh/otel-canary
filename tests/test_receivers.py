import json
import urllib.error
import urllib.request

from opentelemetry.exporter.otlp.proto.http import Compression
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor

from otel_canary.receivers import HTTPReceiver


def _send_span(endpoint: str, **exporter_kwargs: object) -> None:
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(OTLPSpanExporter(endpoint=endpoint, **exporter_kwargs)))
    with provider.get_tracer("test").start_as_current_span("span"):
        pass
    provider.shutdown()


def test_records_a_span_from_the_otlp_http_exporter():
    with HTTPReceiver() as receiver:
        _send_span(f"{receiver.url}/v1/traces", headers={"authorization": "Bearer test"})

    assert receiver.log.spans == 1
    assert receiver.log.accepted_paths() == {"/v1/traces"}
    assert "authorization" in receiver.log.accepted_headers()


def test_decompresses_gzip_requests():
    with HTTPReceiver() as receiver:
        _send_span(f"{receiver.url}/v1/traces", compression=Compression.Gzip)

    assert receiver.log.spans == 1
    assert "content-encoding" in receiver.log.accepted_headers()


def test_accepts_sdk_specific_paths():
    with HTTPReceiver() as receiver:
        _send_span(f"{receiver.url}/api/public/otel/v1/traces")

    assert receiver.log.accepted_paths() == {"/api/public/otel/v1/traces"}


def test_rejects_posts_during_the_outage_window():
    with HTTPReceiver(fail_for_seconds=60) as receiver:
        request = urllib.request.Request(f"{receiver.url}/v1/traces", data=b"", method="POST")
        try:
            urllib.request.urlopen(request)
            status = 200
        except urllib.error.HTTPError as exc:
            status = exc.code

    assert status == 503
    assert receiver.log.posts[0].status == 503
    assert receiver.log.spans == 0


def test_answers_gets_with_the_configured_json():
    with HTTPReceiver(get_responses={"/v1/info": {"project_name": "canary"}}) as receiver:
        configured = json.load(urllib.request.urlopen(f"{receiver.url}/v1/info"))
        default = json.load(urllib.request.urlopen(f"{receiver.url}/anything"))

    assert configured == {"project_name": "canary"}
    assert default == {}
    assert receiver.log.gets == ["/v1/info", "/anything"]


def test_grpc_receiver_records_a_span_and_its_metadata():
    from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter as GRPCSpanExporter

    from otel_canary.receivers import GRPC_EXPORT_PATH, GRPCReceiver

    with GRPCReceiver() as receiver:
        provider = TracerProvider()
        exporter = GRPCSpanExporter(
            endpoint=receiver.url, insecure=True, headers={"authorization": "Bearer t"}
        )
        provider.add_span_processor(SimpleSpanProcessor(exporter))
        with provider.get_tracer("test").start_as_current_span("span"):
            pass
        provider.shutdown()

    assert receiver.log.spans == 1
    assert receiver.log.accepted_paths() == {GRPC_EXPORT_PATH}
    assert "authorization" in receiver.log.accepted_headers()
