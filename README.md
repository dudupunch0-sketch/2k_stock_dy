# 두루미 주식

ChatGPT Work에 짧게 말하면("코스맥스 분석해줘") 공시·시세·컨센서스를 모아 근거가 붙은 투자 분석 HTML을 만들고, 매주 금요일 보유·관심 종목의 변화를 정리하는 도구입니다. 매매 지시는 하지 않습니다.

- 쓰는 법: [docs/USAGE.md](docs/USAGE.md)
- 현재 상태와 다음 할 일: [HANDOFF.md](HANDOFF.md)
- 에이전트 지침: [AGENTS.md](AGENTS.md), Claude 진입점 [CLAUDE.md](CLAUDE.md), Work 명령 규칙 [docs/instructions/chat-commands.md](docs/instructions/chat-commands.md)

## 구성

- `stockdy/`: DART·SEC 수집, 시세(Yahoo)·네이버증권 컨센서스, 재무 정규화(분기/누적/TTM), 상세·주간 HTML 생성기, CLI
- `config/universe.json`: 보유·관심 종목(주간 보고 대상). `universe` 명령으로만 바꾼다. AAPL은 검증용 예시.
- `requests/` → GitHub Actions 수집 → `data/requests/<id>/snapshot.json`, `data/history/`
- `analysis/`: 출처가 붙은 AI 분석 입력. `reports/`: 날짜별 보고서(덮어쓰기 금지)와 `latest.html`
- `docs/instructions/`: Work 실행 규칙과 금요일 주간 보고 지시문
- `tests/`: 네트워크 없이 도는 단위 테스트

## 명령

```sh
python3 -m unittest discover -s tests -t .
python3 -m stockdy.cli universe list
python3 -m stockdy.cli market 192820
python3 -m stockdy.cli report data/requests/<id>/snapshot.json --analysis analysis/<name>.json --refresh-market --out reports/<folder>/YYYY-MM-DD.html
python3 -m stockdy.cli weekly-report data/weekly/YYYY-MM-DD.json --out reports/weekly/YYYY-MM-DD.html
```

DART 키는 GitHub Actions secret으로만 씁니다. 유료 AI API나 상시 서버는 쓰지 않습니다. 시세와 컨센서스는 비공식 원천이라 막히면 해당 칸이 N/A로 나옵니다.
