# 두루미 주식

**개발 이어받기:** [HANDOFF.md](HANDOFF.md)에서 현재 진행 상태와 미완료 항목을 확인하세요. 에이전트 공통 지침은 [AGENTS.md](AGENTS.md), Claude 진입점은 [CLAUDE.md](CLAUDE.md)입니다. 구현은 `feat/stock-analysis-reporting` 브랜치와 Draft PR #1에 있으며 아직 main에 병합하지 않았습니다.

Reusable public-company collection, source-normalized evidence, analysis inputs, and interactive HTML investment records. Actual tracked universe is controlled by config/universe.json. AAPL is a validation fixture and is not a holding/watchlist entry.

## Project layout

- stockdy/: DART and SEC public filing adapters, metric normalization, schema validation, weekly diffs, and self-contained HTML report generators.
- config/universe.json: explicit holdings/watchlist only. Manual on-demand requests do not silently alter this list.
- requests/: per-request queue and completion/error state.
- data/requests/: request-specific source snapshot. data/history/: compact immutable source/evidence packet for comparisons.
- analysis/: AI-authored, sourced company analysis/scenario inputs.
- journal/: user-authored thesis and trading notes, append-only and separate.
- reports/: immutable dated detailed/weekly HTML, with latest.html pointer.
- docs/instructions/: Work runbook and reusable Friday prompt.

## Local commands

python3 -m stockdy.cli collect-apr
python3 -m stockdy.cli collect-sec AAPL
python3 -m stockdy.cli report data/apr/latest.json --analysis analysis/apr.json --out reports/apr/latest.html
python3 -m stockdy.cli weekly-diff PREVIOUS.json CURRENT.json --out reports/weekly/diff.json
python3 -m stockdy.cli weekly-report data/weekly/YYYY-MM-DD.json --out reports/weekly/YYYY-MM-DD.html

Domestic Actions collection reads DART_API_KEY from GitHub Actions secrets. No paid AI API or server is used. The APR snapshot contains DART annuals for FY2021–FY2025 and separately tagged issuer preliminary Q1, Q2, and 1H 2026 values. The 2026 issuer release notes IFRS 18 restated FY2025 comparisons. Prices, portfolio cost basis, consensus, trading flows and other missing values are shown as unavailable, not inferred. Work cloud and scheduled execution require separate live verification.
