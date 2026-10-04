# 구현 재개 체크포인트 (2026-10-04)

- Feature branch: feat/stock-analysis-reporting, baseline 7526758.
- APR evidence: DART 2021–2025 annuals; saved DART 2026 Q1; issuer preliminary 2026 Q2 and 1H data with distinct standalone/YTD basis and IFRS 18 restatement caveat.
- SEC collector resolves arbitrary listed ticker through SEC company_tickers.json and stores selected annual US-GAAP facts rather than full raw companyfacts.
- Request pipeline checks configured holdings/watchlist, creates immutable snapshot and compact history packet, and preserves failure status for Actions to save.
- Output: reports/apr/2026-10-04.html and latest.html; nine detailed analysis sections, finance table, scenario controls and evidence links.
- Work prompt/instructions: docs/instructions/weekly-run.md and workflows.md. Weekly numeric delta: python3 -m stockdy.cli weekly-diff PREVIOUS.json CURRENT.json --out reports/weekly/YYYY-MM-DD.json.
- Verified by syntax compilation and inspecting generated summary metadata only; no test suite was added or run. No DART refresh because the prior temporary local credential file is absent in this resumed WSL context. GitHub Actions DART_API_KEY remains configured per prior setup.
- Not validated here: native Work cloud execution/schedule, Actions execution after merge, current quote, automated news/consensus, portfolio cost-basis personalization. Those stay explicitly unverified/unavailable.
