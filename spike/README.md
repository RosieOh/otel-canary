# M0 스파이크

설계의 핵심 가정을 확인하려고 만든 **버려도 되는 코드**입니다. M1은 이 코드를 참고만 하고 새로 작성합니다.

- `smoke_phoenix.py`: 로컬 OTLP/HTTP 수신기를 띄우고 `phoenix.otel.register()`로 span 하나를 보낸 뒤, `PASS`, `FAIL`, `DEGRADED` 중 하나로 판정해 JSON으로 출력합니다.
- `otel-main-overrides.txt`: OTel core main과 contrib main을 git 소스로 설치하는 uv override 파일입니다. `[urllib3]` 같은 extras를 빠뜨리면 가짜 실패가 납니다.

## 실행

```bash
# 골든 케이스: 0.17.1 × 1.45 는 FAIL 이어야 한다
uv venv v1 && VIRTUAL_ENV=$PWD/v1 uv pip install "arize-phoenix-otel==0.17.1" "opentelemetry-sdk==1.45.0" "opentelemetry-exporter-otlp==1.45.0"
v1/bin/python smoke_phoenix.py

# 수정 버전 × OTel main
uv venv v2 && VIRTUAL_ENV=$PWD/v2 uv pip install "arize-phoenix-otel==0.17.2" --override otel-main-overrides.txt
v2/bin/python smoke_phoenix.py
```

결과는 [../docs/DESIGN.md §17](../docs/DESIGN.md#17-m0-스파이크-결과-2026-09-29)에 정리돼 있습니다.
