# otel-canary 설계 문서

> 상태: **설계 단계, M0 스파이크 완료** (2026-09-29)

## 1. 한 줄 정의

LLM 관측성 SDK들이 OpenTelemetry Python의 **새 버전과 아직 릴리스되지 않은 main**에서도 동작하는지 매일 확인하고, 깨지면 가장 먼저 알려주는 공개 호환성 매트릭스입니다.

## 2. 왜 필요한가

### 2.1 실제로 일어난 일

| 날짜 | 사건 |
|---|---|
| 2026-08-12 | OTel Python [#5389](https://github.com/open-telemetry/opentelemetry-python/pull/5389)가 main에 머지됨. HTTP exporter를 공용 HTTP 클라이언트 구조로 리팩터링 |
| 2026-09-25 | OTel Python 1.45.0 릴리스 |
| 2026-09-25 | arize-otel [#30](https://github.com/Arize-ai/arize-otel-python/issues/30): 1.45에서 `_headers` 오류 |
| 2026-09-25 | W&B Weave가 `opentelemetry-exporter-otlp-proto-http<1.45` 상한 추가 ([#7956](https://github.com/wandb/weave/pull/7956)) |
| 2026-09-26 | rhesis [#2832](https://github.com/rhesis-ai/rhesis/issues/2832): 1.45에서 `_session` 오류 |
| 2026-09-27 | Phoenix [#16547](https://github.com/Arize-ai/phoenix/issues/16547): `register()`가 `AttributeError`로 죽음 → [#16549](https://github.com/Arize-ai/phoenix/pull/16549)로 수정 |

원인이 된 변경은 **릴리스 6주 전부터 main에 있었습니다.** main으로 매일 테스트하는 곳이 있었다면 사용자보다 먼저 잡을 수 있었습니다.

### 2.2 지금 생태계 상태 (2026-09-29, PyPI 메타데이터 기준)

| SDK | 버전 | OTel 제약 | 의미 |
|---|---|---|---|
| arize-phoenix-otel | 0.17.2 | exporter-otlp-proto-http **>=1.45.0** | 1.45 이상만 지원 |
| logfire | 5.1.1 | sdk·exporter **<1.45.0** | 1.45 차단 |
| weave | 0.53.11 | exporter-otlp-proto-http **<1.45** | 1.45 차단 |
| langfuse | 4.15.6 | >=1.33.1, <2 | 1.45에서 동작하는지 **아무도 확인하지 않음** |
| traceloop-sdk | 0.62.3 | >=1.38.0, <2 | 〃 |
| lmnr | 0.7.64 | >=1.39.0, <2 | 〃 |
| agentops | 0.4.21 | >1.29.0 | 〃 |
| mlflow-tracing | 3.16.1 | >=1.9.0, <3 | 〃 |
| arize-otel | 0.14.1 | >=1.22 | 〃 |

그 결과 **같이 설치할 수 없는 조합**이 이미 생겼습니다 (`uv pip compile`로 확인).

| 조합 | 결과 |
|---|---|
| arize-phoenix-otel 0.17.2 + logfire 5.1.1 | **충돌** (>=1.45 vs <1.45) |
| arize-phoenix-otel 0.17.2 + weave 0.53.11 | **충돌** |
| arize-phoenix-otel 0.17.2 + langfuse 4.15.6 | 설치됨, OTel 1.45.0으로 결정 |
| logfire 5.1.1 + langfuse 4.15.6 | 설치됨, OTel 1.44.0으로 결정 |

Langfuse는 함께 설치하는 패키지에 따라 1.44 또는 1.45 위에서 돌게 되는데, 1.45에서 동작하는지 보증하는 곳이 없습니다.

### 2.3 기존 도구로 안 되는 이유

- OTel Python은 자기 contrib 패키지를 main에 대해 테스트합니다(`Core Contrib Test` 워크플로). 하지만 **서드파티 LLM SDK는 대상이 아닙니다.**
- OTel Python은 **nightly 빌드를 배포하지 않습니다.** main을 테스트하려면 git 소스에서 직접 설치해야 합니다.
- Rust에는 생태계 전체 회귀 검사 도구 [crater](https://github.com/rust-lang/crater)가 있습니다. 빠르게 검색해 본 범위에서는 Python·OTel 쪽에 공개된 도구가 없었습니다.

## 3. 목표와 비목표

**목표**

- G1. SDK × OTel 버전 × 전송 방식 매트릭스를 매일 자동 실행
- G2. OTel **main**까지 포함해 릴리스 전에 경보
- G3. 결과를 공개 대시보드와 JSON으로 제공
- G4. 상태가 바뀌면 이 저장소에 추적 이슈를 자동 생성
- G5. 실패 원인을 빨리 좁힐 수 있도록 로그, 버전 스냅샷, OTel 커밋 범위를 함께 남김

**비목표**

- 업스트림 저장소에 이슈나 PR을 **자동으로** 올리는 것. 사람이 확인한 뒤 직접 보고합니다.
- SDK 기능 전체를 테스트하는 것. 스모크 수준만 확인합니다.
- OTel 외 의존성(pydantic, httpx 등) 추적, Go·JS OTel 지원. 둘 다 나중에 고려합니다.

## 4. 테스트 매트릭스

| 축 | MVP 값 | 나중에 |
|---|---|---|
| SDK | arize-phoenix-otel, langfuse, logfire, weave, traceloop-sdk | mlflow-tracing, lmnr, agentops, arize-otel, LiteLLM OTel 콜백, OpenInference 계측기 |
| OTel 버전 | `previous`(1.44.0), `latest`(1.45.0), `main`(git) | 지원 최소 버전 |
| 설치 모드 | `respect-pins`, `force` | — |
| 전송 방식 | HTTP/protobuf, gRPC (SDK가 지원하는 것만) | HTTP/JSON |
| Python | 3.12 | 3.10, 3.13, 3.14 |

- **`respect-pins`**: 사용자가 실제로 받는 조합입니다. SDK가 그 OTel 버전을 막으면 `BLOCKED`로 기록합니다.
- **`force`**: `uv --override`로 OTel 버전을 강제합니다. "상한을 풀면 실제로 깨지는가"를 봅니다. Weave와 Logfire의 상한이 여전히 필요한지 여기서 드러납니다.
- **규모**: SDK 5 × OTel 3 × 모드 2 × 전송 약 1.5 ≈ 45셀입니다. GitHub Actions job은 (SDK, OTel) 단위로 15개를 만들고, job 안에서 모드와 전송 방식을 돕니다.
- `previous`와 `latest`는 PyPI에서 자동으로 계산합니다. 하드코딩하지 않습니다.

## 5. 셀 하나의 실행 과정

```
┌ venv 생성 (uv) ─ 설치 ─ 버전 스냅샷 ─ 가짜 수신기 시작 ─ 스모크 시나리오 ─ 판정 ─ 결과 저장 ┐
```

1. **격리 환경**: 셀마다 새 `uv venv`를 만듭니다.
2. **설치**
   - `respect-pins`: `uv pip install <sdk>==X opentelemetry-sdk==V ...`를 실행합니다. 충돌하면 resolver 메시지를 저장하고 `BLOCKED`로 끝냅니다.
   - `force`: override 파일로 OTel 패키지를 바꿉니다. main은 git 소스를 씁니다 (§8).
3. **버전 스냅샷**: `uv pip freeze` 결과를 그대로 저장합니다.
4. **가짜 수신기**: 로컬 포트에 OTLP 수신기를 띄웁니다.
   - HTTP: 표준 라이브러리 `http.server`로 받고, `ExportTraceServiceRequest`로 protobuf를 파싱합니다.
   - gRPC: `grpcio`로 TraceService를 구현합니다.
5. **스모크 시나리오**: SDK 어댑터(§7)가 초기화 → span 생성 → flush/shutdown을 수행합니다.
6. **판정**: 예외, 수신한 span 수, 필수 속성, 전달된 헤더(인증 헤더 등)로 상태를 정합니다 (§6).
7. **결과 저장**: 셀별 JSON과 로그를 남깁니다.

외부 SaaS로는 아무것도 보내지 않습니다. 비밀값이 필요 없게 만드는 것이 원칙입니다.

## 6. 결과 분류

| 상태 | 뜻 | 경보 |
|---|---|---|
| `PASS` | 예외 없음, 기대한 span 수신 | — |
| `FAIL` | 초기화나 전송 중 예외 (예: `AttributeError`) | ✅ |
| `DEGRADED` | 예외는 없지만 span이 오지 않거나 속성·헤더가 빠짐 | ✅ |
| `BLOCKED` | `respect-pins`에서 설치 불가. SDK가 그 버전을 막은 것이라 버그가 아니라 정보 | 상태가 바뀔 때만 |
| `INFRA` | 네트워크, 빌드 실패, 설치 방식 문제 등 환경 원인 | ❌ (재시도) |

`INFRA`를 따로 두는 이유는 스파이크에서 직접 겪었기 때문입니다 (§14). 재시도해서 통과하면 `FLAKY` 표시를 붙입니다.

## 7. SDK 어댑터

SDK마다 초기화 방법이 달라서, 차이를 어댑터 하나에 가둡니다.

```python
class Adapter(Protocol):
    name: str                  # "phoenix"
    package: str               # "arize-phoenix-otel"
    transports: set[str]       # {"http", "grpc"}

    def run(self, endpoint: str, transport: str) -> None:
        """초기화 → span 1개 이상 생성 → flush. 실패하면 예외를 그대로 던진다."""
```

- **Phoenix**: 스파이크로 확인했습니다. `register(endpoint=..., headers=..., batch=False)`를 부른 뒤 span을 만들고 `force_flush()`를 호출합니다.
- **나머지 SDK는 [docs/adapters.md](adapters.md)에 조사 결과가 있습니다.** 로컬로 보내는 방법, 전송 방식, 계정 필요 여부, 내부 결합, 실측 결과를 SDK별로 정리했습니다. 특히 Logfire는 표준 OTLP 경로가 아니라 **자사 exporter를 거치는 실제 경로**를 테스트해야 합니다.
- 어댑터는 최소 시나리오만 담습니다. SDK API가 바뀌어도 고칠 곳이 적어야 하기 때문입니다.

## 8. 조기 경보: OTel main 설치

main 설치에서 확인한 제약이 두 가지 있습니다.

1. **core만 main으로 올릴 수 없습니다.** contrib의 `opentelemetry-instrumentation 0.66b0`이 `opentelemetry-semantic-conventions==0.66b0`을 정확히 고정하는데, core main은 `0.67b0.dev`입니다. 그래서 core main과 contrib main을 함께 설치해야 합니다.
2. **override는 extras를 지웁니다.** main의 HTTP exporter는 `opentelemetry-exporter-http-transport[urllib3]`에 의존합니다. override 줄에 `[urllib3]`를 빠뜨리면 `urllib3`가 설치되지 않아 가짜 `FAIL`이 납니다.

override 파일은 손으로 쓰지 말고 **패키지 메타데이터에서 extras까지 읽어 생성**해야 합니다.

```text
opentelemetry-exporter-http-transport[urllib3] @ git+https://github.com/open-telemetry/opentelemetry-python.git@main#subdirectory=exporter/opentelemetry-exporter-http-transport
opentelemetry-instrumentation @ git+https://github.com/open-telemetry/opentelemetry-python-contrib.git@main#subdirectory=opentelemetry-instrumentation
```

- 실행할 때마다 core와 contrib main의 커밋 SHA를 기록합니다.
- 새 `FAIL`이 나오면 "마지막으로 통과한 SHA부터 지금 SHA까지"의 커밋 목록을 이슈에 붙입니다. 사람이 원인 PR을 빨리 찾을 수 있습니다.
- 나중에는 자동 bisect로 원인 커밋을 직접 찾게 합니다 (M4).

## 9. 정적 스캔: 내부 속성 결합 탐지 (M4)

런타임 테스트는 "지금 깨졌는가"를 봅니다. 정적 스캔은 "**다음에 깨질 곳**"을 봅니다.

1. OTel 패키지 소스에서 클래스별 내부 속성 목록(`self._x = ...`)을 모읍니다.
2. 각 SDK 설치본의 소스를 AST로 훑어, 외부 객체의 `_x` 접근 중 위 목록과 겹치는 것을 찾습니다.
3. 결과를 SDK별 "결합 목록"으로 보여줍니다.

알려진 예시는 이렇습니다.

- Weave `weave_init.py`: `exporter._session.auth`, `exporter._certificate_file`
- LiteLLM `otlp_json.py`: `self._session.headers`
- **고쳐진 Phoenix도** `exporter._client._headers`에 여전히 의존합니다. 다음 리팩터링에서 또 깨질 수 있습니다. OTel에 헤더를 읽는 공개 API를 제안하는 기여로 이어질 수 있는 지점입니다.

## 10. 산출물과 알림

- **데이터**: `results/<date>.json`을 데이터 전용 브랜치에 누적합니다.
- **대시보드**: 정적 HTML입니다 (`oss-contribution-notes`의 선형 화이트 테마 재사용). 매트릭스 표에서 셀을 누르면 버전 스냅샷, 오류, 로그를 봅니다.
- **배지**: SDK별 shields.io endpoint JSON을 만듭니다.
- **이슈**: 상태가 바뀌면 이 저장소에 이슈를 만들거나 갱신합니다. 라벨은 `sdk/<name>`, `otel/<version>`입니다.
- **업스트림 보고**: 사람이 재현을 확인한 뒤, 재현 코드, 버전, 원인 커밋을 담은 템플릿으로 직접 보고합니다. 각 저장소의 기여 규칙(이슈 먼저, CLA/DCO 등)을 따릅니다.

## 11. 저장소 구조

```
otel-canary/
├── src/otel_canary/
│   ├── cli.py          # otel-canary run
│   ├── runner.py       # 셀 하나: venv → 설치 → 수신기 → 어댑터 → 판정
│   ├── install.py      # uv venv·install, BLOCKED/INFRA 구분, 버전 스냅샷
│   ├── receivers.py    # 가짜 OTLP/HTTP 수신기 (gzip, 장애 주입, GET 응답)
│   ├── classify.py     # PASS / FAIL / DEGRADED / BLOCKED / INFRA 판정
│   └── adapters/       # 셀의 venv에서 도는 SDK별 시나리오 (adapter_<name>.py + _runner.py)
├── tests/              # 단위 테스트 + integration(실제 설치, 골든 케이스)
├── .github/workflows/ci.yml
├── spike/              # M0 검증 코드 (버려도 됨)
└── docs/
```

- M2에서 `matrix.py`(버전 계산), `report.py`(대시보드·배지·상태 변화), `nightly.yml`이 추가됐습니다.
- 어댑터 파일 이름에 `adapter_` 접두사를 붙인 이유: 어댑터 디렉터리가 `sys.path` 맨 앞에 오기 때문에, `phoenix.py`라는 파일이 있으면 진짜 `phoenix` 패키지를 가립니다.

## 12. GitHub Actions 설계

- **트리거**: 매일 UTC 21:00(한국 시간 오전 6시) cron, 그리고 수동 실행(`workflow_dispatch`)
- **job 1 `plan`**: `previous`/`latest` 버전을 계산하고 main SHA를 기록한 뒤 매트릭스 JSON을 출력합니다.
- **job 2 `run`**: (SDK, OTel)마다 job 하나씩 돌고, job 안에서 모드와 전송 방식을 반복합니다. timeout은 10분이고 uv 캐시를 씁니다.
- **job 3 `report`**: 결과를 합쳐 이전 실행과 비교한 뒤, 이슈를 만들거나 갱신하고 대시보드를 배포합니다.
- 공개 저장소라 Linux 러너는 무료입니다. 가짜 수신기만 쓰니 비밀값도 필요 없습니다.

## 13. 마일스톤

| 단계 | 기간 | 내용 | 수용 기준 |
|---|---|---|---|
| **M0** | 완료 | 스파이크: 알려진 사례 재현, main 설치 검증 | §17 |
| **M1** | 완료 (2026-09-29) | CLI, HTTP 수신기, 어댑터 3개(Phoenix, Langfuse, traceloop), 로컬 실행 | 골든 케이스 4개 통과 (`tests/test_golden.py`) |
| **M2** | 구현 완료 (2026-09-29) | gRPC 수신기, 어댑터 5개, nightly Actions, JSON 결과, 정적 대시보드, 상태 변화 이슈 | 3일 연속 무인 실행, 가짜 경보 0건 (관찰 중) |
| **M3** | 3~4주차 | `force` 모드와 `BLOCKED`, main 커밋 범위 첨부, 배지 | Weave·Logfire 상한이 여전히 필요한지 판정 |
| **M4** | 이후 | 정적 결합 스캔, 자동 bisect, 어댑터 확장, 케이스 스터디 글 | — |

## 14. 위험과 대응

| 위험 | 대응 |
|---|---|
| 설치 방식이 만드는 가짜 실패 | `INFRA` 분류, override에 extras 보존, 재시도, 사람이 확인하기 전 업스트림 보고 금지. 스파이크에서 실제로 겪음: `[urllib3]` 누락 → 가짜 `ModuleNotFoundError` |
| SDK가 계정이나 네트워크를 요구 (Weave 등) | 가짜 엔드포인트로 돌리는 방법 조사. 불가능하면 제외하고 대시보드에 이유 표시 |
| SDK API 변경으로 어댑터 유지보수 부담 | 어댑터를 최소 시나리오로 유지, SDK 버전도 스냅샷에 기록 |
| 업스트림에 소음 유발 | 자동 보고 금지, 검증된 것만 사람이 보고 |
| 매트릭스 폭발 | MVP 축을 좁게 시작, 셀 수를 대시보드에 표시 |

## 15. 성공 지표 (6개월)

- 가짜 경보 비율 5% 미만 (`INFRA` 제외)
- OTel 릴리스 전(main 단계)에 잡은 깨짐 건수
- 업스트림에 보고한 이슈·PR 수와 그중 반영된 수
- (부차적) 저장소 스타, 대시보드 방문

## 16. 첫 주에 해볼 일

1. GitHub에 `otel-canary` 공개 저장소를 만듭니다. 설명(description)은 "Daily compatibility canary for LLM observability SDKs against OpenTelemetry Python releases and main"을 씁니다.
2. ~~어댑터 조사 표를 만듭니다.~~ 완료: [docs/adapters.md](adapters.md)
3. **M1을 구현합니다.** `spike/`와 조사 문서는 참고만 하고 새로 작성합니다. 작업 단위는 GitHub 이슈(M1 마일스톤)로 나눠 두었습니다.
4. 골든 케이스(이슈 #7의 네 셀)가 기대대로 판정되는지 확인합니다.

## 17. M0 스파이크 결과 (2026-09-29)

`spike/smoke_phoenix.py`: 로컬 HTTP 수신기를 띄우고 `phoenix.otel.register()`로 span 하나를 보내 판정합니다.

| 셀 | 결과 | 비고 |
|---|---|---|
| phoenix-otel 0.17.1 × OTel 1.44.0 | `PASS` | span 1개 수신 |
| phoenix-otel 0.17.1 × OTel 1.45.0 | `FAIL` | `AttributeError: 'HTTPSpanExporter' object has no attribute '_headers'` (이슈 #16547 재현) |
| phoenix-otel 0.17.2 × OTel 1.45.0 | `PASS` | 수정 버전 |
| phoenix-otel 0.17.2 × OTel main (1.46.0.dev / 0.67b0.dev) | `PASS` | core + contrib main을 override로 설치 |

**알게 된 것**

- 첫 main 실행은 `ModuleNotFoundError: urllib3`로 실패했습니다. OTel 버그가 아니라, override가 `[urllib3]` extras를 지운 설치 문제였습니다. `INFRA` 분류와 extras 보존이 왜 필요한지 보여주는 사례입니다.
- 수신한 헤더를 비교했더니, 1.44는 `accept`와 `connection`을 보내고 1.45는 보내지 않았습니다. 전송 계층이 requests에서 urllib3로 바뀐 흔적입니다. 버그는 아니지만, 헤더 비교만으로 이런 **동작 변화**를 잡을 수 있다는 뜻입니다. `DEGRADED` 판정에 쓸 수 있습니다.

## 18. 어댑터 조사에서 나온 소견 (2026-09-29)

자세한 내용은 [docs/adapters.md](adapters.md)에 있습니다.

- **traceloop-sdk 0.62.3은 지금 깨끗한 환경에서 설치하면 동작하지 않습니다.** `requests`와 `httpx`를 import하지만 둘 다 의존성으로 선언하지 않았습니다. OTel 1.45(기본 설치)에서는 `requests`에서, 1.44로 고정하면 `httpx`에서 `ModuleNotFoundError`가 납니다. 처음엔 OTel 1.45가 원인이라고 봤지만, 1.44로 다시 돌려 보고 원인이 더 넓다는 걸 확인했습니다. [traceloop/openllmetry#4526](https://github.com/traceloop/openllmetry/issues/4526)으로 보고했습니다.
- **Weave의 1.45 상한은 필요합니다.** 강제로 1.45를 설치하면 `_session` 속성 오류로 실패합니다.
- **Logfire의 1.45 상한도 필요합니다.** 강제 1.45에서 `requests`를 추가하면 정상 경로는 통과하지만, 수신기가 15초 동안 503을 돌려주는 장애 주입에서는 span이 유실됐습니다. 1.45가 세션의 `request()`를 불러 Logfire가 `post()`에 걸어둔 디스크 재시도를 우회하기 때문입니다. [pydantic/logfire#2497](https://github.com/pydantic/logfire/issues/2497)로 알렸습니다.
- **설계 보강 (장애 주입)**: 정상 경로 스모크는 재시도 같은 실패 경로의 회귀를 잡지 못합니다. 수신기가 일정 시간 503을 돌려준 뒤 회복하는 **장애 주입 시나리오**를 M3 후보로 추가하고, `DEGRADED` 판정(장애 뒤 미도착)에 씁니다.
- **설계 보강 (의존성)**: 1.45 깨짐의 큰 유형은 "선언되지 않은 의존성"이었습니다. SDK가 import하는 모듈이 선언된 의존성으로 설치되는지 검사하는 기능을 M3 후보로 추가합니다.
