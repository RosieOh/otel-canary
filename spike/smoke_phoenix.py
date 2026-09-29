"""Spike: does phoenix-otel export a span over OTLP/HTTP to a local mock receiver?"""
import http.server
import json
import sys
import threading

from opentelemetry.proto.collector.trace.v1.trace_service_pb2 import ExportTraceServiceRequest

received = {"requests": 0, "spans": 0, "headers": []}


class Receiver(http.server.BaseHTTPRequestHandler):
    def do_POST(self):
        body = self.rfile.read(int(self.headers.get("Content-Length", 0)))
        req = ExportTraceServiceRequest()
        req.ParseFromString(body)
        received["requests"] += 1
        received["spans"] += sum(len(ss.spans) for rs in req.resource_spans for ss in rs.scope_spans)
        received["headers"] = sorted(k.lower() for k in self.headers.keys())
        self.send_response(200)
        self.end_headers()

    def log_message(self, *args):
        pass


server = http.server.HTTPServer(("127.0.0.1", 0), Receiver)
threading.Thread(target=server.serve_forever, daemon=True).start()
endpoint = f"http://127.0.0.1:{server.server_port}/v1/traces"

result = {"status": "PASS"}
try:
    from phoenix.otel import register

    tp = register(project_name="canary", endpoint=endpoint, headers={"authorization": "Bearer t"},
                  batch=False, set_global_tracer_provider=False, verbose=False)
    with tp.get_tracer("canary").start_as_current_span("smoke"):
        pass
    tp.force_flush()
    if received["spans"] < 1:
        result["status"] = "DEGRADED"
except Exception as e:  # crash during init or export is the failure we are looking for
    result = {"status": "FAIL", "error": f"{type(e).__name__}: {e}"}

import importlib.metadata as md

result.update(received, versions={p: md.version(p) for p in [
    "arize-phoenix-otel", "opentelemetry-sdk", "opentelemetry-exporter-otlp-proto-http", "opentelemetry-semantic-conventions"]})
print(json.dumps(result))
sys.exit(0 if result["status"] == "PASS" else 1)
