# Work weekly run prompt

Follow docs/instructions/workflows.md. Run each Friday at 10:00 Asia/Seoul. Analyze configured holdings and watchlist only. Read the latest successful report and compact evidence packets under data/history; read raw filings only to verify specific claims.

Compare seven days since the prior successful run. Include only source-backed changes in filings, earnings, material company news, and upcoming events. Cite regulator, issuer, or original broker pages and dates. Separate confirmed results, issuer guidance, individual broker forecasts, consensus, and AI scenarios. If nothing changed, say “확인된 중요 변화 없음”. State missing inputs, inaccessible sources, and quote price/time if known. Report token usage as unmeasured unless the account exposes it.

Write a compact structured change summary and a self-contained interactive HTML at reports/weekly/YYYY-MM-DD.html. Preserve dated reports and update the latest pointer only after success. Keep AI analysis separate from the user journal. Do not invent price, news, schedules, forecasts, or market statistics. User decides add/partial-sale actions; no trade order or share quantity.
