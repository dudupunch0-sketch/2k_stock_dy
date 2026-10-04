# 짧은 채팅 명령 처리 규칙 (Work 프로젝트 "두루미 주식")

저장소: GitHub `dudupunch0-sketch/2k_stock_dy`, 브랜치 `main`. 공통 규칙은 `docs/instructions/workflows.md`를 따른다.

## 종목 식별

- 사용자는 이름만 말할 수 있다(예: "삼성전자"). 국내는 6자리 종목코드와 시장 `KRX`, 미국은 티커와 거래소(`NASDAQ`/`NYSE`, 모르면 `US`)로 바꾼다.
- 국내 종목의 `corp_code`는 알면 넣고, 모르면 비워 둔다. Actions가 DART에서 자동으로 찾는다.
- 이름이 여러 종목에 해당하거나 확실하지 않으면 실행 전에 후보를 보여주고 한 번 물어본다.

## 명령

| 사용자 말 | 할 일 |
|---|---|
| "X 분석해줘" | 상세 분석만 한다. 요청 파일 → 수집 → `analysis/<id>.json` 작성 → HTML 생성. 추적 목록에는 등록하지 않는다. |
| "X 추가해줘" / "X 관심 종목에 추가" | `config/universe.json`의 `watchlist`에 등록한다. 기준 자료가 없으면 이어서 최초 상세 분석을 한다. |
| "X 보유로 추가" / "X 샀어" | `holdings`에 등록한다. 수량·원가는 사용자가 말한 경우에만 `notes`에 적는다. 최초 분석은 위와 같다. |
| "X 빼줘" / "X 삭제" | 목록에서 빼기 전에 한 번 확인받는다. 과거 보고서와 근거는 지우지 않는다. |
| "목록 보여줘" | 현재 보유/관심 종목과 각 종목의 최신 보고서 경로를 보여준다. |
| "주간 보고 지금 해줘" | `docs/instructions/weekly-run.md`를 지금 실행한다. |

- 한도: 보유 3개, 관심 10개(`limits`). 초과하면 등록하지 말고 알린다.
- `validation_fixtures`(AAPL 등)는 실제 목록이 아니다. 건드리지 않는다.

## 상세 분석 실행 순서

1. `requests/<ticker소문자>-<YYYYMMDD>.json` 작성 후 main에 푸시한다. 필드: `request_id`(파일명과 같게), `ticker`, `market`, `company_name`, `kind: "detailed"`, `user_requested: true`, `period_years: 5`, `requested_at`, `status: "pending"`, 국내는 알면 `corp_code`, 미국은 알면 `cik`. 같은 id가 이미 있으면 `-2`, `-3`을 붙인다.
2. Actions "Collect requested public filings"가 끝나면 main을 다시 받는다. 요청이 `fulfilled`인지 확인한다. `failed`/`rejected`이면 오류를 그대로 보고하고 멈춘다.
3. `data/requests/<id>/snapshot.json`와 `data/history/<ticker>/...`를 읽고, 출처가 있는 근거로 `analysis/<ticker>.json`을 작성하거나 갱신한다. 형식은 `analysis/apr.json`을 따른다.
4. `python3 -m stockdy.cli report data/requests/<id>/snapshot.json --analysis analysis/<ticker>.json --out reports/<ticker>/<YYYY-MM-DD>.html`를 실행하고, 같은 명령에 `--out reports/<ticker>/latest.html`을 붙여 한 번 더 실행한다. 날짜 파일이 이미 있으면 `-2` 같은 새 이름을 쓴다.
5. 바뀐 파일을 main에 커밋/푸시한다. 한국어 3~5줄 요약과 HTML 다운로드를 첨부한다.

## 금지

- 매수/매도 지시나 수량을 쓰지 않는다. 시나리오는 가정으로 표시한다.
- 출처가 없는 수치나 날짜를 만들지 않는다. 없으면 N/A와 이유를 쓴다.
- 비밀값을 출력하거나 파일에 쓰지 않는다. 다른 사용자 파일·과거 보고서·일기를 수정하지 않는다.
