# SDK 어댑터 조사

> 2026-09-29 조사. SDK마다 설치본의 소스를 직접 읽고, 로컬 가짜 OTLP 수신기로 span 하나를 보내 확인했습니다.
> 조사용 코드는 저장소에 넣지 않았습니다. 어댑터는 M1에서 이 표를 보고 새로 작성합니다.

## 1. 요약

| SDK (버전) | 로컬로 보내는 방법 | 전송 방식 | 계정 필요 | 기본 설치 (respect-pins) | OTel 1.45 강제 (force) |
|---|---|---|---|---|---|
| arize-phoenix-otel 0.17.2 | `register(endpoint=...)` | HTTP, gRPC | 아니오 | OTel 1.45 · **PASS** | — (기본이 1.45) |
| langfuse 4.15.6 | `Langfuse(public_key, secret_key, base_url=...)` | HTTP | 아니오 (가짜 키로 충분) | OTel 1.45 · **PASS** | — (기본이 1.45) |
| logfire 5.1.1 | 실제 경로: `configure(token=..., advanced=AdvancedOptions(base_url=...))` | HTTP | 아니오 (가짜 토큰으로 충분) | OTel 1.44 · **PASS** | **FAIL** `requests` 없음 → `requests` 추가 시 PASS |
| traceloop-sdk 0.62.3 | `Traceloop.init(api_endpoint=..., telemetry_enabled=False)` | HTTP(`http://`), gRPC(`grpc://`) | 아니오 | OTel 1.45 · **FAIL** `requests` 없음 | — (기본이 1.45) |
| weave 0.53.11 | 비공개 함수 `_setup_conversation_tracing()` + `WF_TRACE_SERVER_URL` | HTTP | 공개 경로는 W&B 계정 필요 | OTel 1.44 · **PASS** | **FAIL** `_session` 없음 |

## 2. SDK별 상세

### arize-phoenix-otel

- **진입점**: `phoenix.otel.register(endpoint=..., headers=..., batch=False, set_global_tracer_provider=False)`
- **확인 방법**: 반환된 TracerProvider로 span을 만들고 `force_flush()`를 호출합니다.
- **내부 결합**: `exporter._client._headers` (§9 정적 스캔 대상). 1.45 수정 이후에도 내부 속성을 읽습니다.
- **골든 케이스**: 0.17.1 × 1.45 = `FAIL` (`_headers` 없음), 0.17.2 × 1.45 = `PASS` (M0 스파이크)

### langfuse

- **진입점**: `Langfuse(public_key="pk-...", secret_key="sk-...", base_url=<수신기>)` 후 `start_as_current_observation(name=...)`, 끝나면 `flush()`
- **전송 경로**: `{base_url}/api/public/otel/v1/traces`입니다. `LANGFUSE_OTEL_TRACES_EXPORT_PATH`로 바꿀 수 있습니다.
- **헤더**: `Authorization: Basic <public:secret>`, `x-langfuse-sdk-name`, `x-langfuse-sdk-version`, `x-langfuse-public-key`
- **환경변수**: `LANGFUSE_PUBLIC_KEY`, `LANGFUSE_SECRET_KEY`, `LANGFUSE_BASE_URL`(또는 `LANGFUSE_HOST`)
- **OTel 사용 방식**: 공개 인자만 씁니다 (`OTLPSpanExporter(endpoint, headers, timeout)`, `BatchSpanProcessor` 상속). 코드의 `session=` 인자는 점수 수집 클라이언트용이라 OTel과 무관합니다.
- **결과**: OTel 1.45 · PASS (span 1개, 인증 헤더 전달 확인)

### logfire

- **진입점이 두 개**라서 **실제 경로**를 테스트해야 합니다.
  - 표준 OTLP 환경변수 경로: `OTEL_EXPORTER_OTLP_TRACES_ENDPOINT` + `configure(send_to_logfire=False)`. 기본 `OTLPSpanExporter()`만 거칩니다.
  - **실제 경로**: `configure(token="pylf_v1_us_...", send_to_logfire=True, advanced=logfire.AdvancedOptions(base_url=<수신기>))`. Logfire가 자사 백엔드로 보낼 때 쓰는 `BodySizeCheckingOTLPSpanExporter`, 커스텀 `requests.Session`(`OTLPExporterHttpSession`), gzip 압축을 모두 거칩니다.
- **부수 요청**: 토큰 확인 스레드가 `GET {base_url}/v1/info`를 부릅니다. 가짜 수신기가 `{}`를 돌려주면 스레드에서 `KeyError: 'project_name'`이 나지만 판정과는 무관합니다. 수신기는 SDK별로 그럴듯한 응답을 돌려주는 게 좋습니다.
- **내부 결합**: `processor._batch_processor`, `batch_processor._exporter` (`BatchSpanProcessor` 내부)
- **버전 제약**: `opentelemetry-sdk<1.45.0`, `opentelemetry-exporter-otlp-proto-http<1.45.0`
- **결과**
  - OTel 1.44 (기본): 두 경로 모두 PASS
  - OTel 1.45 강제: 두 경로 모두 **FAIL** `ModuleNotFoundError: No module named 'requests'`. logfire 5.1.1은 `requests`를 필수 의존성으로 선언하지 않습니다.
  - OTel 1.45 강제 + `requests` 설치: 두 경로 모두 **PASS**. 스모크 수준에서는 상한의 원인이 `requests` 선언 누락뿐일 수 있습니다. 다만 커스텀 세션의 재시도(DiskRetryer) 동작은 확인하지 않았습니다. **추가 확인 필요.**

### traceloop-sdk

- **진입점**: `Traceloop.init(app_name=..., api_endpoint=<수신기>, headers=..., disable_batch=True, telemetry_enabled=False)` 후 `@workflow` 데코레이터로 span 생성, 마지막에 전역 TracerProvider의 `force_flush()`
- **전송 방식 선택**: `http://`와 `https://`는 HTTP exporter(`/v1/traces` 자동 추가), `grpc://`와 `grpcs://`는 gRPC exporter, 스킴이 없으면 gRPC입니다.
- **원격 전송**: `telemetry_enabled=False`로 꺼야 외부 네트워크를 쓰지 않습니다.
- **결과**: OTel 1.45 (기본 설치) · HTTP와 gRPC 모두 **FAIL**
  ```
  File ".../traceloop/sdk/images/image_uploader.py", line 5, in <module>
      import requests
  ModuleNotFoundError: No module named 'requests'
  ```
  - traceloop-sdk 0.62.3은 `fetcher.py`, `images/image_uploader.py`, `datasets/attachment.py`, `client/http.py`에서 `requests`를 import하지만 의존성으로 선언하지 않습니다.
  - OTel 1.44까지는 HTTP exporter가 `requests`를 끌고 들어와 가려져 있었습니다. 1.45에서 exporter가 urllib3로 바뀌면서, 깨끗한 환경에 `pip install traceloop-sdk`만 하면 `from traceloop.sdk import Traceloop`에서 바로 죽습니다.
  - 2026-09-29 기준 traceloop/openllmetry에 관련 이슈가 없고, main의 `pyproject.toml`에도 `requests`가 없습니다. 같은 유형의 사례로 appsignal-python [#291](https://github.com/appsignal/appsignal-python/issues/291)이 있습니다.

### weave

- **공개 진입점** `weave.init()`은 W&B 인증과 서버 통신을 거친 뒤에 OTel exporter를 만듭니다. 계정 없이는 돌릴 수 없습니다.
- **대안**: 비공개 함수 `weave.trace.weave_init._setup_conversation_tracing(entity, project, credentials=None)`을 직접 부르고, `WF_TRACE_SERVER_URL`을 수신기로 지정합니다. 전송 경로는 `/agents/otel/v1/traces`입니다. 비공개 함수라 어댑터가 쉽게 깨질 수 있어, 실패하면 `INFRA`와 구분해 표시해야 합니다.
- **내부 결합**: `exporter._session.headers`, `exporter._session.auth`, `exporter._certificate_file`
- **결과**
  - OTel 1.44 (기본): PASS
  - OTel 1.45 강제: **FAIL** `AttributeError: 'OTLPSpanExporter' object has no attribute '_session'`. 상한이 실제로 필요합니다.

## 3. 설계에 반영할 점

1. **스모크는 SDK의 실제 전송 경로를 타야 한다.** Logfire를 표준 OTLP 경로로만 테스트하면 자사 exporter와 커스텀 세션을 놓칩니다.
2. **"선언되지 않은 의존성"이 1.45 깨짐의 큰 유형이다.** traceloop, Logfire, appsignal이 모두 `requests`를 OTel을 통해 간접적으로 얻고 있었습니다. 설치 단계에서 "SDK가 import하는 모듈이 SDK의 선언 의존성으로 설치되는가"를 따로 검사하는 기능을 고려합니다 (`import` 목록과 `requires_dist` 비교).
3. **수신기는 부수 요청에도 그럴듯하게 답해야 한다.** Logfire의 `GET /v1/info` 같은 요청이 있습니다.
4. **force 모드는 상한이 여전히 필요한지 판정할 수 있다.** 이번 조사에서 Weave는 "필요함", Logfire는 "`requests` 선언으로 풀릴 가능성 있음"으로 나왔습니다.

## 4. 업스트림에 보고할 수 있는 소견

| 대상 | 내용 | 상태 |
|---|---|---|
| traceloop/openllmetry | traceloop-sdk가 `requests`를 선언하지 않아 OTel 1.45 환경에서 import 실패 | 미보고 (2026-09-29) |
| pydantic/logfire | `requests` 선언 누락. 선언하면 1.45 상한을 풀 수 있는지 논의 | 재시도 경로 확인 뒤 판단 |
