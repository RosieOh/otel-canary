# 기여처 분석 스크립트

2026년 9월에 기여할 저장소와 이슈를 고를 때 쓴 스크립트입니다. `gh auth token`으로 GitHub API를 부르니 `gh`에 로그인돼 있어야 합니다.

| 파일 | 하는 일 |
|---|---|
| `pr_speed.py` | 공용 모듈(HTTP·GraphQL 호출, 날짜 분할 검색)입니다. 직접 실행하면 최근 60일 머지 PR 기준으로 외부인 PR 머지 속도를 잽니다. |
| `pr_cohort.py` | 코호트 방식 측정입니다. 6/30~8/28에 fork로 올라온 외부인 PR(메인테이너·봇·다작자 제외)이 지금 어떻게 됐는지 추적합니다. `index.html`의 표가 이 결과입니다. |
| `policy_check.py` | 외부 PR이 닫힌 이유(마지막 코멘트)와 CONTRIBUTING의 규칙 키워드(할당, AI, CLA, DCO)를 샘플링합니다. |
| `find_issues.py` | 라벨 기준으로 담당자·연결된 PR·선점 코멘트가 없는 이슈를 찾습니다. |
| `radar.py` | 최근 며칠 안에 올라온 이슈 중 선점 표현이 없는 것을 여러 저장소에서 한꺼번에 찾습니다. |
| `summarize.py` | `pr_speed.py` 결과를 표로 출력합니다. |

```bash
python3 pr_cohort.py out.json          # 저장소 목록은 파일 안의 REPOS
python3 radar.py 2026-09-24            # 이 날짜 이후 생성된 이슈
```

`data/`의 JSON은 2026-09-27 기준 스냅샷입니다.

## 주의

- 비공개 org 멤버는 API에서 `CONTRIBUTOR`로 보여서, 메인테이너가 외부인으로 섞일 수 있습니다. 그래서 fork에서 올라왔는지(`isCrossRepository`)와 PR 개수(3개 이하)로 한 번 더 거릅니다.
- 선점 감지는 정규식이라 놓치는 표현이 있습니다 (예: "I have a small patch ready"). 추천하기 전에 이슈 본문을 직접 읽어야 합니다.
- Google ADK처럼 Copybara로 내부에서 머지하는 저장소는 GitHub의 머지 통계가 의미가 없습니다.
