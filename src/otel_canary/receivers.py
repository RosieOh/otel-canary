"""Mock OTLP receivers that record what an SDK under test sends (docs/DESIGN.md §5)."""

from __future__ import annotations

import gzip
import http.server
import json
import threading
import time
from dataclasses import asdict, dataclass, field
from typing import Any

from opentelemetry.proto.collector.trace.v1.trace_service_pb2 import (
    ExportTraceServiceRequest,
    ExportTraceServiceResponse,
)


@dataclass
class Post:
    path: str
    status: int
    spans: int
    headers: list[str]
    at: float


@dataclass
class ReceiverLog:
    posts: list[Post] = field(default_factory=list)
    gets: list[str] = field(default_factory=list)

    @property
    def spans(self) -> int:
        """Spans in requests the receiver accepted."""
        return sum(post.spans for post in self.posts if post.status == 200)

    def accepted_paths(self) -> set[str]:
        return {post.path for post in self.posts if post.status == 200}

    def accepted_headers(self) -> set[str]:
        return {header for post in self.posts if post.status == 200 for header in post.headers}

    def summary(self) -> dict[str, Any]:
        return {
            "spans": self.spans,
            "requests": len(self.posts),
            "posts": [asdict(post) for post in self.posts],
            "gets": list(self.gets),
        }


def count_spans(request: ExportTraceServiceRequest) -> int:
    return sum(len(scope.spans) for resource in request.resource_spans for scope in resource.scope_spans)


class HTTPReceiver:
    """OTLP/HTTP (protobuf) receiver on 127.0.0.1; `url` is the base URL without a path.

    Any POST path is accepted, since SDKs use their own (for example Langfuse's
    `/api/public/otel/v1/traces`). With `fail_for_seconds`, POSTs get `fail_status` until that
    many seconds after start, to exercise an SDK's retry path. GETs answer 200 with `{}` unless
    `get_responses` maps the path to another JSON body.
    """

    def __init__(
        self,
        fail_for_seconds: float = 0.0,
        fail_status: int = 503,
        get_responses: dict[str, Any] | None = None,
    ) -> None:
        self.log = ReceiverLog()
        self._fail_for_seconds = fail_for_seconds
        self._fail_status = fail_status
        self._get_responses = get_responses or {}
        self._lock = threading.Lock()
        self._started_at = 0.0
        self._server: http.server.ThreadingHTTPServer | None = None
        self.url = ""

    def __enter__(self) -> HTTPReceiver:
        receiver = self

        class Handler(http.server.BaseHTTPRequestHandler):
            def do_POST(self) -> None:
                body = self.rfile.read(int(self.headers.get("Content-Length", 0)))
                elapsed = time.monotonic() - receiver._started_at
                status = receiver._fail_status if elapsed < receiver._fail_for_seconds else 200
                spans = 0
                if status == 200:
                    if self.headers.get("Content-Encoding", "").lower() == "gzip":
                        body = gzip.decompress(body)
                    request = ExportTraceServiceRequest()
                    try:
                        request.ParseFromString(body)
                        spans = count_spans(request)
                    except Exception:  # not OTLP/protobuf; record the request with no spans
                        spans = 0
                with receiver._lock:
                    receiver.log.posts.append(
                        Post(
                            path=self.path,
                            status=status,
                            spans=spans,
                            headers=sorted(name.lower() for name in self.headers.keys()),
                            at=round(elapsed, 3),
                        )
                    )
                self.send_response(status)
                self.send_header("Content-Type", "application/x-protobuf")
                self.end_headers()
                if status == 200:
                    self.wfile.write(ExportTraceServiceResponse().SerializeToString())

            def do_GET(self) -> None:
                with receiver._lock:
                    receiver.log.gets.append(self.path)
                body = json.dumps(receiver._get_responses.get(self.path, {})).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def log_message(self, format: str, *args: Any) -> None:  # noqa: A002 - stdlib signature
                pass

        self._server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self._started_at = time.monotonic()
        threading.Thread(target=self._server.serve_forever, daemon=True).start()
        self.url = f"http://127.0.0.1:{self._server.server_port}"
        return self

    def __exit__(self, *exc: object) -> None:
        if self._server is not None:
            self._server.shutdown()
            self._server.server_close()
