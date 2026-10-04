# 두루미 주식 사용법

## 1. 보고서 보기

| 보고서 | 위치 |
|---|---|
| 종목 상세 분석 최신본 | `reports/<종목>/latest.html` (예: `reports/apr/latest.html`) |
| 종목 상세 분석 날짜별 | `reports/<종목>/YYYY-MM-DD*.html` — 덮어쓰지 않고 쌓임 |
| 주간 보고 | `reports/weekly/YYYY-MM-DD.html`, 최신 성공본은 `reports/weekly/latest.html` |

- 저장소를 받은 뒤 HTML 파일을 더블클릭하면 브라우저에서 열린다. 인터넷 없이도 열리는 단일 파일이다.
- GitHub에서 보려면 파일 → Download raw file로 받아서 연다. ChatGPT Work 대화에 첨부된 다운로드 링크를 써도 된다.
- 보고서 안에서: 요약 → 강점/위험 → 재무 추세 → 시나리오(이익 성장률·PER 슬라이더로 다시 계산) → 9개 상세 항목(눌러서 펼침) → 재무표·원문 링크 순서다.
- 숫자에는 출처·기준일이 붙는다. 자료가 없으면 이유와 함께 `N/A`로 표시된다.

## 2. 종목 상세 분석 요청 (필요할 때만)

ChatGPT → **Work** → 프로젝트 **두루미 주식** → 모델 **GPT-6 Luna / Medium**을 고른 뒤 이렇게 요청한다.

> 연결된 GitHub 저장소 dudupunch0-sketch/2k_stock_dy 의 main에서 docs/instructions/workflows.md 를 따라 **삼성전자(005930) 상세 분석**을 해줘. 요청 파일을 만들어 수집을 실행하고, 결과로 분석을 작성해 HTML 보고서를 만들어 커밋하고 다운로드 링크를 첨부해줘.

Work가 하는 일:
1. `requests/<요청id>.json` 생성·푸시
2. GitHub Actions가 공시 수집(국내: DART, 미국: SEC) → 요청 상태 `fulfilled`
3. Work가 근거를 읽고 `analysis/<종목>.json` 작성 → Python 생성기로 HTML 생성·커밋

국내 종목은 DART 고유번호(corp_code)가 필요하다. 모르면 Work에게 찾아달라고 한다.
상세 분석을 요청해도 보유/관심 목록에 자동으로 추가되지는 않는다.

## 3. 보유/관심 종목 등록 (주간 보고 대상)

`config/universe.json`의 `holdings`(보유) 또는 `watchlist`(관심)에 종목을 추가한다. Work에게 "삼성전자를 관심 종목에 추가해줘"라고 요청해도 된다. 현재 등록 종목은 보유 에이피알(278470) 하나다.

## 4. 주간 자동 보고

- ChatGPT 예약 작업 **"[두루미 주식 주간 보고]"**: 매주 금요일 오전 10:00(한국 표준시), GPT-6 Luna Medium, 실행할 때마다 새 채팅.
- 등록 종목의 최근 7일 공시·실적·뉴스·추정치 변화와 다음 일정을 조사하고, `data/weekly/`와 `reports/weekly/`에 저장한다.
- 확인 및 수정: https://chatgpt.com/scheduled
- 첫 실행은 2026-10-09다. 실제 예약 실행이 GitHub까지 정상 작동하는지는 첫 실행 결과로 확인해야 한다.

## 5. 투자 일기

내 메모는 `journal/<종목>.jsonl`에 기록하며 AI 분석과 분리해 보존한다. 지금 보고서 화면은 메모를 읽어 보여주지 않는다.

## 6. 주의

- 매수/매도 지시나 수량은 생성하지 않는다. 시나리오는 AI 가정이며 판단은 사용자가 한다.
- 현재 주가·PER/PBR·수급·경쟁사 비교·컨센서스는 아직 자동 수집되지 않는다.
- DART 키는 GitHub Actions secret으로만 쓴다. 파일이나 대화에 붙여넣지 않는다.
- ChatGPT 5시간 사용량이 부족하면 Work 실행이 중간에 멈출 수 있다. 상세 분석 1회는 약 6분이 걸렸다(수집 테스트 기준).
