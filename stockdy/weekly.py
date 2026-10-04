"""Render validated, self-contained weekly research reports."""
from __future__ import annotations
import datetime as dt
import html
import json
import shutil
from pathlib import Path
from urllib.parse import urlparse
from .core import ROOT

CATEGORIES = {"filing", "earnings", "news", "schedule", "estimate", "guidance", "corporate_action", "other"}


def _safe_url(value):
    p = urlparse(str(value or ""))
    return str(value) if p.scheme in ("https", "http") and p.netloc else ""


def _date(value):
    try:
        return dt.date.fromisoformat(str(value)[:10])
    except (TypeError, ValueError):
        return None


def _tracked_tickers():
    universe = json.loads((ROOT / "config/universe.json").read_text(encoding="utf-8"))
    return {str(x.get("ticker", "")).upper() for x in universe.get("holdings", []) + universe.get("watchlist", []) if x.get("ticker")}


def build_weekly_report(data: dict, out: Path):
    end = _date(data.get("week_ending") or data.get("as_of"))
    start = _date(data.get("period_start"))
    if not start or not end or start > end or (end - start).days > 6:
        raise ValueError("Weekly period must be valid ISO dates covering at most seven calendar days")
    start_s, end_s = start.isoformat(), end.isoformat()
    tracked = _tracked_tickers()
    exclusions = list(data.get("unverified_or_unavailable", []))
    covered = {str(x.get("ticker", "")).upper() for x in data.get("coverage", []) if x.get("ticker")}
    coverage = list(data.get("coverage", []))
    for item in coverage:
        state = str(item.get("status", "")).strip().lower()
        if state not in {"success", "covered", "no_change", "confirmed", "확인됨"}:
            exclusions.append(f"{str(item.get('ticker', '종목')).upper()}: 주간 확인 상태 {state or '미제공'}")
    for ticker in sorted(tracked - covered):
        coverage.append({"ticker": ticker, "status": "not covered"})
        exclusions.append(f"{ticker}: 주간 확인 범위에 포함되지 않음")
    changes, events = [], []
    allowed_categories = CATEGORIES
    for idx, item in enumerate(data.get("changes", []), 1):
        ticker = str(item.get("ticker", "")).upper()
        published = _date(item.get("published_at"))
        url = _safe_url(item.get("source"))
        category = str(item.get("category", "")).lower()
        reason = None
        if ticker not in tracked: reason = "추적 목록 밖 종목"
        elif not url: reason = "출처 링크가 유효하지 않음"
        elif category not in allowed_categories: reason = "지원하지 않는 분류"
        elif not published or not start <= published <= end: reason = "발행일이 주간 범위 밖이거나 확인되지 않음"
        if reason:
            exclusions.append(f"변경 항목 {idx}: {reason}; 보고서에서 제외")
            continue
        changes.append({**item, "ticker": ticker, "published_at": published.isoformat(), "source": url})
    for idx, item in enumerate(data.get("upcoming_events", []), 1):
        ticker = str(item.get("ticker", "")).upper()
        day = _date(item.get("date"))
        url = _safe_url(item.get("source"))
        category = str(item.get("category", "schedule")).lower()
        reason = None
        if ticker not in tracked: reason = "추적 목록 밖 종목"
        elif not url: reason = "출처 링크가 유효하지 않음"
        elif category not in allowed_categories: reason = "지원하지 않는 분류"
        elif not day or day < end: reason = "일정 날짜가 확인되지 않거나 기준일 이전"
        if reason:
            exclusions.append(f"일정 {idx}: {reason}; 보고서에서 제외")
            continue
        events.append({**item, "ticker": ticker, "date": day.isoformat(), "source": url})
    status = "success" if data.get("status") == "success" and not exclusions else "partial"
    payload = json.dumps({"changes": changes, "events": events}, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")

    def cards(items, kind):
        if not items: return "<p class=empty>확인된 항목 없음</p>"
        return "".join(f'<article class=entry data-ticker="{html.escape(str(x["ticker"]), quote=True)}" data-kind="{html.escape(str(x.get("category", kind)), quote=True)}"><small>{html.escape(str(x.get("published_at") or x.get("date")))} · {html.escape(x["ticker"])} · {html.escape(str(x.get("category", kind)))}</small><h3>{html.escape(str(x.get("headline", "제목 미제공")))}</h3><p>{html.escape(str(x.get("summary", "")))}</p><a href="{html.escape(x["source"], quote=True)}" target="_blank" rel="noopener">원문 확인 ↗</a></article>' for x in items)

    coverage_html = "".join(f'<li>{html.escape(str(x.get("ticker", x.get("name", "종목"))))}: {html.escape(str(x.get("status", "확인")))}</li>' for x in coverage) or "<li>대상 종목 상태 미기록</li>"
    missing = "".join(f"<li>{html.escape(str(x))}</li>" for x in exclusions) or "<li>기록된 누락 항목 없음</li>"
    report = f'''<!doctype html><html lang=ko><meta charset=utf-8><meta name=viewport content="width=device-width,initial-scale=1"><title>두루미 주식 주간 기록 {html.escape(end_s)}</title><style>{CSS}</style><body><header><nav>두루미 주식 <span>{html.escape(end_s)} · 주간 변화</span></nav><p class=eyebrow>WEEKLY INVESTMENT JOURNAL</p><h1>이번 주 확인된 변화</h1><p>{html.escape(str(data.get("summary", "요약 없음")))}</p><div class=callout>기준: {html.escape(start_s)} – {html.escape(end_s)} · 상태: {status}</div></header><main><section><h2>대상 종목</h2><ul>{coverage_html}</ul></section><section><h2>근거 필터</h2><div class=filters><label>종목 <select id=ticker><option value=all>전체</option></select></label><label>유형 <select id=kind><option value=all>전체</option>{''.join(f'<option value="{x}">{x}</option>' for x in sorted(allowed_categories))}</select></label><label>검색 <input id=q type=search placeholder="제목이나 요약"></label><span id=count></span></div><div id=changes class=grid>{cards(changes, "change")}</div></section><section><h2>다가오는 일정</h2><div class=grid>{cards(events, "schedule")}</div></section><section><h2>자료가 없어 확인하지 못한 항목</h2><ul>{missing}</ul></section><section><h2>기록 기준</h2><p>확정 실적, 회사 가이던스, 개별 증권사 전망, 컨센서스, AI 가정은 서로 다른 종류의 정보입니다. 이 페이지는 사용자의 검토를 돕기 위한 변경 기록이며 매매 신호가 아닙니다.</p></section></main><footer>모델 생성 요약은 링크된 원문과 대조해 주세요. 조회되지 않은 값은 추정하지 않았습니다.</footer><script>const D={payload};{JS}</script></body></html>'''
    out = Path(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    if out.exists():
        if out.read_text(encoding="utf-8") != report:
            raise FileExistsError(f"Dated report is immutable and already exists: {out}")
    else:
        out.write_text(report, encoding="utf-8")
    if status == "success":
        latest = out.parent / "latest.html"
        if out.resolve() != latest.resolve(): shutil.copy2(out, latest)
    return out

CSS = """*{box-sizing:border-box}body{margin:0;background:#f3f5f1;color:#1b2924;font:16px/1.6 system-ui,-apple-system,sans-serif}header{background:#153b33;color:#fff;padding:28px max(22px,calc((100vw - 1050px)/2)) 40px}nav{display:flex;justify-content:space-between;color:#bed2c9}.eyebrow{margin-top:42px;letter-spacing:.14em;font-size:.75rem;color:#a7c9bd}h1{font-size:clamp(2rem,6vw,4rem);line-height:1.05;letter-spacing:-.05em;margin:.2em 0}header>p:not(.eyebrow){max-width:780px;color:#d4e1dc}.callout{padding:12px 16px;background:#ffffff18;border-radius:12px;display:inline-block}main{max-width:1050px;margin:auto;padding:24px 20px 60px}section{margin:30px 0 48px}.filters{display:flex;gap:12px;align-items:end;flex-wrap:wrap;background:#e7eeea;padding:16px;border-radius:14px}.filters label{display:grid;gap:5px}.filters input,.filters select{min-width:170px;padding:9px;border:1px solid #c9d6cf;border-radius:8px;background:#fff}.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(260px,1fr));gap:14px;margin-top:15px}.entry{background:#fff;padding:18px;border:1px solid #e0e8e2;border-radius:14px}.entry small{color:#64766d}.entry h3{line-height:1.3}.entry a{color:#22674e}.empty{padding:18px;color:#697b72}.hidden{display:none}footer{text-align:center;padding:24px;border-top:1px solid #dce4df;color:#71817b;font-size:.85rem}@media(max-width:600px){header{padding:20px}main{padding:14px}}"""
JS = """const cards=[...document.querySelectorAll('.entry')],t=document.querySelector('#ticker'),k=document.querySelector('#kind'),q=document.querySelector('#q');for(const x of [...new Set([...D.changes,...D.events].map(x=>x.ticker).filter(Boolean))]){const o=document.createElement('option');o.value=x;o.textContent=x;t.append(o)}function apply(){let n=0;for(const c of cards){const ok=(t.value==='all'||c.dataset.ticker===t.value)&&(k.value==='all'||c.dataset.kind===k.value)&&c.innerText.toLowerCase().includes(q.value.toLowerCase());c.classList.toggle('hidden',!ok);if(ok)n++}document.querySelector('#count').textContent=n+' items'}for(const x of [t,k,q])x.addEventListener('input',apply);apply();"""
