# otel-canary

LLM 관측성 SDK가 OpenTelemetry Python의 **새 버전과 main 브랜치**에서도 동작하는지 매일 확인하는 호환성 카나리입니다.

> Daily compatibility canary for LLM observability SDKs against OpenTelemetry Python releases and `main`.

- **상태**: M3 완료 — OTel main(미릴리스)과 force 모드까지 매일 확인 (2026-09-29)
- **대시보드**: https://rosieoh.github.io/otel-canary/
- **설계**: [docs/DESIGN.md](docs/DESIGN.md)
- **스파이크**: [spike/](spike/) (검증용 코드, 버려도 됨)

## 사용법

[uv](https://docs.astral.sh/uv/)가 필요합니다. 셀마다 격리된 가상환경을 만들어 SDK와 OpenTelemetry를 설치하고, 로컬 가짜 OTLP 수신기로 span이 제대로 도착하는지 봅니다.

```bash
uv sync
uv run otel-canary run --sdk arize-phoenix-otel==0.17.1 --otel 1.45.0
```

결과는 JSON으로 나오고, 종료 코드는 `PASS` 0, `FAIL` 1, `DEGRADED` 2, `BLOCKED` 3, `INFRA` 4입니다.

| SDK | 어댑터 | 전송 방식 |
|---|---|---|
| arize-phoenix-otel | `phoenix.otel.register()` | HTTP, gRPC |
| langfuse | `Langfuse(...)` 클라이언트 | HTTP |
| traceloop-sdk | `Traceloop.init()` + `@workflow` | HTTP, gRPC |
| logfire | 자사 exporter 경로 (`AdvancedOptions(base_url=...)`) | HTTP |
| weave | 비공개 `_setup_conversation_tracing()` | HTTP |

셀은 SDK × 전송 방식마다 네 가지를 봅니다.

| 열 | 설치 방식 | 알려주는 것 |
|---|---|---|
| previous release | SDK가 허용하는 대로 직전 OTel 릴리스 | 사용자가 지금 받는 조합이 동작하는가 |
| latest release | SDK가 허용하는 대로 최신 OTel 릴리스 | 〃 |
| latest, SDK bounds ignored | SDK의 버전 상한을 무시하고 최신 릴리스를 강제 | 상한이 여전히 필요한가 |
| main (unreleased) | OTel core·contrib main을 그날의 커밋으로 설치 | 다음 릴리스에서 깨질 곳 (조기 경보) |

override로 설치한 셀은 먼저 OTel exporter를 직접 만들어 보고, 실패하면 SDK 탓이 아니라 설치 문제(`INFRA`)로 분류합니다.

매일 도는 흐름은 `plan`(PyPI에서 최신 SDK와 OTel 직전·최신 버전 계산, main 커밋 고정) → `run`(셀마다 GitHub Actions job 하나) → `report`(대시보드, 배지, 상태 변화)입니다. 셀 상태가 PASS에서 FAIL/DEGRADED로 바뀌면 `canary-alert` 이슈를 열고, 회복하면 닫습니다.

```bash
uv run otel-canary plan                                  # 오늘의 매트릭스
uv run otel-canary run --sdk weave==0.53.11 --otel 1.45.0 --mode force   # 상한 무시
uv run otel-canary run --sdk arize-phoenix-otel --otel main                # OTel main
uv run otel-canary report results/ --out site/           # 결과 JSON 모음 → 대시보드
```

```bash
uv run pytest                   # 단위 테스트
uv run pytest -m integration    # 실제 SDK 설치 + 골든 케이스 (네트워크 필요)
```

## 왜

2026년 9월 OpenTelemetry Python 1.45가 릴리스되자 Phoenix, arize-otel, rhesis 같은 SDK가 한꺼번에 깨졌고, Weave는 급히 버전 상한을 걸었습니다. 원인이 된 변경은 릴리스 6주 전부터 main에 있었습니다. 이 프로젝트는 그런 깨짐을 사용자보다 먼저 찾는 것이 목표입니다.

## 면책

OpenTelemetry 프로젝트나 CNCF와 관계없는 개인 프로젝트입니다. 이름의 "otel"은 테스트 대상을 가리킬 뿐, 공식 도구라는 뜻이 아닙니다.

> This is an independent project, not affiliated with or endorsed by the OpenTelemetry project or the CNCF.

## 라이선스

[Apache License 2.0](LICENSE)
