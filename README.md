# 두루미 주식

재사용 가능한 종목 조사 수집기, 증거 패킷, 공통 HTML 보고서를 보관합니다. 초도 실제 분석은 APR(278470)이며 AAPL은 SEC 연결 검증 표본으로만 관리합니다.

- 수집 데이터 계약: config/universe.json, requests/, data/
- 공개 재무 수집: OpenDART 국내, SEC companyfacts 미국
- 구조화된 분석 및 사용자 일기: analysis/, journal/
- 보고서: reports/apr/YYYY-MM-DD.html, reports/weekly/
- Work 절차와 주간 실행 프롬프트: docs/instructions/
- 실행: python3 -m stockdy.cli --help

APR 자료는 5개 완료 연도(2021–2025), 2026 1Q DART 및 2Q/1H 회사 잠정 IR 발표를 포함합니다. DART key는 GitHub Actions 비밀값으로만 주입합니다. Actions / Work Cloud 예약은 저장소 로컬 실행으로 검증되지 않았습니다. 현재가, 한경컨센서스, 수급과 여러 비공개 운영 지표는 미수집이며 보고서에서 미확인으로 표시합니다.
