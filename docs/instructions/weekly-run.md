# Work weekly run prompt

Follow docs/instructions/workflows.md. Run Fridays at 10:00 Asia/Seoul. Use only configured holdings/watchlist from config/universe.json. Read the prior successful report and compact evidence packets under data/history. Compare the seven calendar days ending today with the prior successful run. Add only source-backed filings, results, company news, analyst/consensus updates, and upcoming events. Link regulator, issuer, original broker, or credible direct news pages; include publication dates and distinguish estimates from facts. If nothing changed, say 확인된 중요 변화 없음. Record source gaps and access failures; never invent prices, news, dates, estimates, market values, or financial facts.

For each Korean ticker run `python3 -m stockdy.cli market <ticker>` once. Compare its consensus (next-year EPS, operating income), average target price and 5-day foreign/institution net buying with the previous weekly JSON or the latest snapshot `naver` block. Record a material change (for example consensus EPS or target price moving 5% or more, or a new broker report) as category `estimate` with `published_at` = the Naver consensus/report date and `source` = the Naver URL in the output; call it 컨센서스(FnGuide) or the named broker, never a company fact. If the command reports errors, list them in unverified_or_unavailable.

Create data/weekly/YYYY-MM-DD.json with this structure:

{
  "week_ending": "YYYY-MM-DD",
  "period_start": "YYYY-MM-DD",
  "status": "success",
  "summary": "Source-backed Korean summary",
  "coverage": [{"ticker": "278470", "status": "success"}],
  "changes": [{"ticker": "278470", "category": "news", "published_at": "YYYY-MM-DD", "headline": "...", "summary": "...", "source": "https://..."}],
  "upcoming_events": [{"ticker": "278470", "category": "schedule", "date": "YYYY-MM-DD", "headline": "...", "summary": "...", "source": "https://..."}],
  "unverified_or_unavailable": []
}

Coverage must include every configured holding/watchlist ticker. Use success, covered, no_change, confirmed, or 확인됨 only after checking that ticker; use another status for a gap, which makes the report partial. Categories are filing, earnings, news, schedule, estimate, guidance, corporate_action, and other. Every change needs a publication date within the seven-day range and an HTTP(S) original source. Upcoming events need a valid date on or after the week-ending date and a source. Invalid, unsupported, out-of-range, and off-list rows are excluded and recorded as limitations; any exclusion or coverage gap prevents a success status.

Render with:
python3 -m stockdy.cli weekly-report data/weekly/YYYY-MM-DD.json --out reports/weekly/YYYY-MM-DD.html

This creates a self-contained interactive report. The dated output is immutable; an identical rerun is safe, but changed evidence needs a new dated filename. reports/weekly/latest.html changes only after a successful report. Preserve dated reports and previous user journal entries. Do not provide buy/sell orders or share quantities. The user decides.
