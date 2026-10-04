# Claude 시작 지침

이 저장소의 공통 지침은 **AGENTS.md**, 현재 상태와 다음 작업은 **HANDOFF.md**를 읽는다. 먼저 두 파일과 현재 Git 상태를 확인한다.

- 작업 위치: `C:\Users\82105\Documents\ChatGPT\2k_stock_dy` / WSL `/mnt/c/Users/82105/Documents/ChatGPT/2k_stock_dy`
- `main` 기준으로 작업하고, 변경은 브랜치 → PR로 올린다. 병합은 사용자가 한다.
- WSL과 Chrome을 사용하고, 비밀값을 공개하지 않는다.
- 코드를 바꾸면 `python3 -m unittest discover -s tests -t .`를 실행한다. 실제 외부 조회·Work 실행 확인과 테스트 통과를 구분해 보고한다.
- 실제로 확인하지 않은 것(예: 주간 예약 실행 결과, 모바일 실행)을 완료로 보고하지 않는다.
- 변경 내용과 확인 결과를 짧은 한국어로 알려주고, 상태가 바뀌면 HANDOFF.md를 현재 상태 기준으로 고쳐 쓴다(이어 붙이지 않는다).
