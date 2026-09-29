# SDK 어댑터 조사

> 2026-09-29 조사. SDK마다 설치본의 소스를 직접 읽고, 로컬 가짜 OTLP 수신기로 span 하나를 보내 확인했습니다.
> 조사용 코드는 저장소에 넣지 않았습니다. 어댑터는 M1에서 이 표를 보고 새로 작성합니다.

## 1. 요약

| SDK (버전) | 로컬로 보내는 방법 | 전송 방식 | 계정 필요 | 기본 설치 (respect-pins) | OTel 1.45 강제 (force) |
|---|---|---|---|---|---|
| arize-phoenix-otel 0.17.2 | `register(endpoint=...)` | HTTP, gRPC | 아니오 | OTel 1.45 · **PASS** | — (기본이 1.45) |
| langfuse 4.15.6 | `Langfuse(public_key, secret_key, base_url=...)` | HTTP | 아니오 (가짜 키로 충분) | OTel 1.45 · **PASS** | — (기본이 1.45) |
| logfire 5.1.1 | 실제 경로: `configure(token=..., advanced=AdvancedOptions(base_url=...))` | HTTP | 아니오 (가짜 토큰으로 충분) | OTel 1.44 · **PASS** | **FAIL** `requests` 없음 → `requests` 추가 시 PASS |
| traceloop-sdk 0.62.3 | `Traceloop.init(api_endpoint=..., telemetry_enabled=False)` | HTTP(`http://`), gRPC(`grpc://`) | 아니오 | OTel 1.45 · **FAIL** `requests` 미선언 (1.44에서도 `httpx` 미선언으로 FAIL) | — (기본이 1.45) |
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
  - OTel 1.45 강제 + `requests` 설치: 두 경로 모두 정상 경로 스모크는 **PASS**. 하지만 **장애 주입 실험에서 FAIL**:
    수신기가 처음 15초 동안 503을 돌려주게 하면, OTel 1.44에서는 배치가 `DiskRetryer`로 넘어가 장애 뒤(20~26초)에 도착하지만,
    OTel 1.45에서는 약 8초 만에 재시도를 포기하고 span이 **유실**됩니다. 1.45의 `RequestsHTTPTransport`가 세션의 `post()`가 아니라
    `request()`를 부르는데, Logfire는 재시도와 디스크 재시도를 `post()`에만 걸어두었기 때문입니다 (main에서도 동일).
    → **상한은 필요합니다.** `requests` 선언은 Logfire main에서 이미 고쳐졌습니다(`logfire-sdk`). [pydantic/logfire#2497](https://github.com/pydantic/logfire/issues/2497)로 알렸습니다.

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
  - traceloop-sdk 0.62.3은 import하는 순간 **`requests`와 `httpx`를 모두 쓰지만, 둘 다 의존성으로 선언하지 않습니다.**
    - `requests`: `client/http.py`, `datasets/attachment.py`, `fetcher.py`, `images/image_uploader.py`
    - `httpx`: `client/client.py`, `evaluator/evaluator.py`, `evaluator/stream_client.py`, `experiment/experiment.py`, `guardrail/guardrail.py`
  - 그래서 깨끗한 환경에서는 **OTel 버전과 상관없이** import가 실패합니다.
    - OTel 1.45 (기본 설치): `requests`에서 실패. 1.45 exporter가 더 이상 `requests`를 끌고 오지 않습니다.
    - OTel 1.44 고정: `requests`는 exporter를 통해 들어오지만, `httpx`에서 실패합니다.
  - OpenAI SDK처럼 `httpx`를 설치하는 패키지와 함께 쓰는 경우가 많아 가려져 있었던 것으로 보입니다.
  - 처음에는 "OTel 1.45 때문"이라고 판단했지만, 1.44로 고정해서 다시 돌려 보고 원인이 더 넓다는 걸 알았습니다. **버전 하나만 보고 원인을 단정하면 안 된다**는 사례입니다.
  - **보고함**: [traceloop/openllmetry#4526](https://github.com/traceloop/openllmetry/issues/4526) (2026-09-29). 같은 유형의 사례로 appsignal-python [#291](https://github.com/appsignal/appsignal-python/issues/291)이 있습니다.

### weave

- **공개 진입점** `weave.init()`은 W&B 인증과 서버 통신을 거친 뒤에 OTel exporter를 만듭니다. 계정 없이는 돌릴 수 없습니다.
- **대안**: 비공개 함수 `weave.trace.weave_init._setup_conversation_tracing(entity, project, credentials=None)`을 직접 부르고, `WF_TRACE_SERVER_URL`을 수신기로 지정합니다. 전송 경로는 `/agents/otel/v1/traces`입니다. 비공개 함수라 어댑터가 쉽게 깨질 수 있어, 실패하면 `INFRA`와 구분해 표시해야 합니다.
- **내부 결합**: `exporter._session.headers`, `exporter._session.auth`, `exporter._certificate_file`
- **결과**
  - OTel 1.44 (기본): PASS
  - OTel 1.45 강제: **FAIL** `AttributeError: 'OTLPSpanExporter' object has no attribute '_session'`. 상한이 실제로 필요합니다.

## 3. 설계에 반영할 점

1. **스모크는 SDK의 실제 전송 경로를 타야 한다.** Logfire를 표준 OTLP 경로로만 테스트하면 자사 exporter와 커스텀 세션을 놓칩니다.
2. **"선언되지 않은 의존성"이 큰 유형이다.** traceloop, Logfire, appsignal이 모두 `requests`를 OTel을 통해 간접적으로 얻고 있었고, traceloop은 `httpx`도 선언하지 않았습니다. 설치 단계에서 "SDK가 import하는 모듈이 SDK의 선언 의존성으로 설치되는가"를 따로 검사하는 기능을 고려합니다 (`import` 목록과 `requires_dist` 비교).
3. **수신기는 부수 요청에도 그럴듯하게 답해야 한다.** Logfire의 `GET /v1/info` 같은 요청이 있습니다.
4. **force 모드는 상한이 여전히 필요한지 판정할 수 있다.** 이번 조사에서 Weave와 Logfire 모두 "필요함"으로 나왔습니다. Logfire는 정상 경로만 봤을 때 "풀려도 될 것 같다"는 **틀린 결론**이 나왔고, 장애 주입으로 뒤집혔습니다.
5. **정상 경로 스모크만으로는 부족하다.** 재시도처럼 실패할 때만 도는 경로의 회귀는 수신기가 일정 시간 오류를 돌려주는 **장애 주입 시나리오**가 있어야 잡힙니다.

## 4. 업스트림에 보고할 수 있는 소견

| 대상 | 내용 | 상태 |
|---|---|---|
| traceloop/openllmetry | traceloop-sdk가 `requests`와 `httpx`를 선언하지 않아 깨끗한 환경에서 import 실패 | 이슈 [#4526](https://github.com/traceloop/openllmetry/issues/4526), 수정 PR [#4527](https://github.com/traceloop/openllmetry/pull/4527) (2026-09-29) |
| pydantic/logfire | OTel 1.45의 requests 전송 계층이 `OTLPExporterHttpSession`의 재시도·디스크 재시도를 우회 (상한을 올릴 때 주의) | [#2497](https://github.com/pydantic/logfire/issues/2497) 보고 (2026-09-29) |
